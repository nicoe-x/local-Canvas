import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'open_studio/_canvas'))
from canvas_h3 import compile_prompt
class ReferenceCompilerTests(unittest.TestCase):
 def test_base_to_ref_preserves_dialogue_and_sound(self):
  source='integrated_multimodal_description: <Picture 1> walks in <Picture 2>. (S1) says: <d>[Chinese] 我到了。</d>\noverall_soundscape: Cicadas.\nnon_diegetic_music: N/A'
  result=compile_prompt(source,['a','b'],7,'写实')
  for value in ['subject_definitions:','summary:','retention_analysis:','detailed_description: [Shot 1]','<d>[Chinese] 我到了。</d>','overall_soundscape: Cicadas.']:self.assertIn(value,result)
  self.assertNotIn('integrated_multimodal_description:',result)
 def test_complete_reference_document_is_unchanged(self):
  value=compile_prompt('A woman walks.', ['a'],5,'写实');self.assertEqual(value,compile_prompt(value,['a'],5,'写实'))
 def test_unknown_reference_and_partial_template_rejected(self):
  for value in ['<Picture 3> walks.','integrated_multimodal_description: incomplete']:
   with self.assertRaises(ValueError):compile_prompt(value,['a'],5,'写实')
