"""Private H3 adapter tests: stage ordering, truthful fallback and frame coverage."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class FacePassTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder/'original.mp4').write_bytes(b'original')
        progress = types.ModuleType('video_progress')
        progress.probe = lambda path: {'streams':[{'codec_type':'video','width':1024,'height':576}]}
        progress.render_clip = lambda *a,**kw: None
        checks = types.ModuleType('media_checks');checks.collect = lambda folder: {}
        cancel = types.ModuleType('job_cancel');cancel.check_cancelled = lambda folder: None
        pause = types.ModuleType('job_pause');pause.checkpoint = lambda folder: None
        self.mods = patch.dict(sys.modules, video_progress=progress, media_checks=checks,
                               job_cancel=cancel, job_pause=pause)
        self.mods.start();self.addCleanup(self.mods.stop)
        spec = importlib.util.spec_from_file_location('face_adapter', Path(__file__).parents[1]/'integrations/h3-private/video_upscale.py')
        self.module = importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.states=[]

    def finish(self, payload):
        self.module.finish(self.folder, payload, 'a'*32, lambda *a,**kw: self.states.append((a,kw)))
        return self.states[-1]

    def test_disabled_keeps_original_and_native_never_calls_enhance(self):
        with patch.object(self.module,'enhance') as enhance:
            state, detail = self.finish({'video_resolution':'native'})
        enhance.assert_not_called()
        self.assertEqual(b'original',(self.folder/'final.mp4').read_bytes())
        self.assertEqual('DISABLED', detail['face_repair']['state'])
        self.assertEqual('COMPLETED_UNREVIEWED',state[0])

    def test_native_runs_independent_pass_and_records_result(self):
        def enhance(folder,payload,job_id,status,**kw):
            self.assertTrue(kw['face_only']);self.assertTrue(payload['video_face_refine'])
            (folder/'final.mp4').write_bytes(b'repaired')
            return {'state':'COMPLETED','face_windows':1}
        with patch.object(self.module,'enhance',side_effect=enhance):
            _, detail = self.finish({'face_repair':True,'video_resolution':'native'})
        self.assertEqual('COMPLETED',detail['face_repair']['state'])
        self.assertEqual(b'original',(self.folder/'original.mp4').read_bytes())
        self.assertEqual(b'repaired',(self.folder/'face-repaired.mp4').read_bytes())
        self.assertEqual('COMPLETED',json.loads((self.folder/'face-repair.json').read_text())['state'])

    def test_upscale_consumes_face_result_without_second_face_diffusion(self):
        calls=[]
        def enhance(folder,payload,job_id,status,**kw):
            calls.append(kw)
            if kw.get('face_only'):
                (folder/'final.mp4').write_bytes(b'repaired');return {'state':'COMPLETED'}
            self.assertFalse(payload['video_face_refine'])
            self.assertEqual(b'repaired',kw['source'].read_bytes())
            raise RuntimeError('upscale failed')
        with patch.object(self.module,'enhance',side_effect=enhance):
            _, detail=self.finish({'face_repair':True,'video_resolution':'2K'})
        self.assertEqual(2,len(calls));self.assertEqual('FAILED',detail['upscale']['state'])
        self.assertEqual(b'repaired',(self.folder/'final.mp4').read_bytes())

    def test_failure_and_no_face_are_not_reported_as_repaired(self):
        for value in [RuntimeError('detector missing'),{'state':'SKIPPED','reason':'no_safe_track'}]:
            mock = patch.object(self.module,'enhance',side_effect=value) if isinstance(value,Exception) else patch.object(self.module,'enhance',return_value=value)
            with mock:
                _,detail=self.finish({'face_repair':True,'video_resolution':'native'})
            self.assertNotEqual('COMPLETED',detail['face_repair']['state'])
            self.assertTrue(detail['upscale_warning'])
            self.assertEqual(b'original',(self.folder/'final.mp4').read_bytes())

    def test_uncertain_submission_must_reconcile_not_fall_back(self):
        class Uncertain(RuntimeError):needs_attention=True
        with patch.object(self.module,'enhance',side_effect=Uncertain('pending')):
            with self.assertRaises(Uncertain):self.finish({'face_repair':True})
        self.assertFalse(any(state[0]=='COMPLETED_UNREVIEWED' for state,_ in self.states))


if __name__=='__main__':unittest.main()
