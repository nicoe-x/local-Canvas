import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT=Path(__file__).parents[1]
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'integrations/h3-private'/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class ResampleTests(unittest.TestCase):
    def setUp(self):
        self.module=load('video_resample_test','video_resample.py')

    def test_probe_rejects_unsupported_timing_size_and_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'clip.mp4';path.write_bytes(b'video')
            def inspect(**kwargs):
                video={'codec_type':'video','width':1024,'height':576,'avg_frame_rate':'24/1','nb_frames':'175',**kwargs}
                result=types.SimpleNamespace(stdout=json.dumps({'streams':[video,{'codec_type':'audio'}]}))
                with patch.object(self.module.subprocess,'run',return_value=result):return self.module.inspect_source(path)
            self.assertEqual(175,inspect()['frames'])
            for args in [dict(avg_frame_rate='30/1'),dict(width=1920,height=1088),dict(width=1023),dict(nb_frames='361')]:
                with self.assertRaises(ValueError):inspect(**args)

    def test_partial_denoise_graph_uses_encoded_source_and_locks_audio(self):
        base={
            '1':{'class_type':'MiniMaxH3AudioConditioningT8','inputs':{}},
            '2':{'class_type':'MiniMaxH3MultiRateSamplerEXPT8','inputs':{'model':['model',0]}},
            '3':{'class_type':'VAELoader','inputs':{'vae_name':'h3_video_vae'}},
            '4':{'class_type':'SamplerCustomAdvanced','inputs':{'sampler':['2',1],'sigmas':['2',2]}},
            '5':{'class_type':'RandomNoise','inputs':{}},
            '6':{'class_type':'MiniMaxH3AVDecodeT8','inputs':{}},
            '7':{'class_type':'VHS_VideoCombine','inputs':{'audio':['6',1]}}}
        pipeline=types.ModuleType('pipeline.t8_render');pipeline.build_t8_graph=lambda *a,**k:base
        policy=types.ModuleType('video_prompt');policy.configure_ref2va_graph=lambda g,**k:self.assertTrue(k['native'])
        with patch.dict(sys.modules,{'pipeline.t8_render':pipeline,'video_prompt':policy}):
            graph=self.module.graph('h3web/id/source.mp4','a'*32,{'frames':48,'width':1024,'height':576},
                                    {'steps':8,'denoise':.25,'seed':123})
        self.assertEqual(56,graph['resample_source']['inputs']['frame_load_cap'])
        self.assertEqual(['resample_encode',0],graph['resample_latent']['inputs']['video_latent'])
        self.assertEqual('lock',graph['resample_latent']['inputs']['audio_mode'])
        self.assertEqual('strict',graph['resample_latent']['inputs']['audio_fit_policy'])
        self.assertEqual(['resample_latent',0],graph['4']['inputs']['latent_image'])
        self.assertEqual(.25,graph['2']['inputs']['denoise']);self.assertEqual(8,graph['2']['inputs']['steps'])
        self.assertEqual(48,graph['resample_trim']['inputs']['length']);self.assertNotIn('audio',graph['7']['inputs'])
        self.assertEqual(123,graph['5']['inputs']['noise_seed'])

    def test_invalid_options_fail_without_sampling(self):
        for value in [{'steps':8,'denoise':float('nan'),'seed':1},{'steps':True,'denoise':.3,'seed':1},
                      {'steps':8,'denoise':.3,'seed':-1},{'steps':8,'denoise':.3,'seed':None}]:
            with self.assertRaises(ValueError):self.module.validate_options(value)

    def test_checked_overlay_refuses_unknown_version_and_tracks_parent_deletion(self):
        installer=load('install_video_resample_test','install_video_resample.py')
        with self.assertRaises(ValueError):installer.patch('gateway/runner.py','unrecognized version')
        source="""OR json_extract(payload,'$.upscale_of')=?) LIMIT 1
(job_id, job_id, job_id, job_id),
for k in ("retry_of", "asset_reuse_of", "upscale_of"): pass
for k in ("retry_of", "asset_reuse_of", "upscale_of"): pass
"""
        result=installer.patch('studio/app.py',source)
        self.assertEqual(3,result.count('resample_of'));self.assertIn('(job_id, job_id, job_id, job_id, job_id)',result)


if __name__=='__main__':unittest.main()
