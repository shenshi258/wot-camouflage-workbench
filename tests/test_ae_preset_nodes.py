"""Preset descriptions and covers use the same authored node playback."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from wotcamo import ae_effects as ae, ae_presets as presets


class PresetNodeDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.clip=ae.pack_frames([Image.new('RGBA',(16,8),(255,40,20,128))],self.root/'source.png')
        self.values=ae.config(dict(fps=4,animation=dict(duration=2,canvas_scale=2,
            nodes=[dict(time=0,opacity=100),dict(time=1,opacity=0),dict(time=2,opacity=100)])))
        self.data,self.payload=presets.encode('节点预设','用途：中点淡出。',self.clip,self.values)
        self.path=presets.store(self.data,self.payload,self.root/'library')

    def test_summary_and_description_report_baked_and_source_timing_without_mutation(self):
        before=copy.deepcopy(self.data)
        text=presets.summary(self.data);description=presets.description_text(self.data)
        self.assertEqual(len(text.splitlines()),2)
        self.assertIn('节点动画 8 帧 · 2 秒',text);self.assertIn('源素材 1 帧',text)
        self.assertIn('节点动画 8 帧 / 4 FPS / 2 秒',description)
        self.assertIn('源素材 1 帧 / 0.25 秒',description)
        self.assertEqual(self.data,before)

    def test_fractional_duration_is_described_as_the_same_quantized_loop(self):
        values=ae.config(dict(self.values,fps=10,animation=dict(duration=.26,nodes=[dict(time=0)])))
        data,unused=presets.encode('量化时长','',self.clip,values)
        self.assertIn('节点动画 3 帧 · 0.3 秒',presets.summary(data))
        self.assertIn('3 帧 / 10 FPS / 0.3 秒',presets.description_text(data))

    def test_over_limit_nodes_are_labelled_invalid_and_never_silently_baked(self):
        values=ae.config(dict(self.values,fps=60,animation=dict(duration=60,nodes=[dict(time=0)])))
        data,payload=presets.encode('超过帧数','',self.clip,values)
        path=presets.store(data,payload,self.root/'oversized')
        self.assertIn('节点动画无效：3600 帧，超过 128 帧',presets.summary(data))
        self.assertIn('请缩短时长或降低帧率',presets.description_text(data))
        with patch.object(ae,'playback_clip') as bake,self.assertRaisesRegex(ValueError,'3600.*128'):
            presets.poster(path)
        bake.assert_not_called();self.assertEqual(path.read_bytes(),payload)

    def test_cover_keeps_the_authored_transparent_midpoint(self):
        with patch.object(ae,'playback_clip',wraps=ae.playback_clip) as playback:
            cover=presets.poster(self.path)
        playback.assert_called_once()
        self.assertEqual(cover.mode,'RGB');self.assertEqual(cover.size,(32,16))
        self.assertTrue(np.all(np.asarray(cover)==np.array([20,25,35])))
        # The source picture is visible: a background-only cover is the node
        # fade at one second, not a fallback to an invisible original frame.
        self.assertEqual(self.clip['frames'],1)
        with Image.open(self.clip['atlas']) as source:
            self.assertGreater(source.getchannel('A').getextrema()[1],0)

    def test_cover_matches_transforms_and_appearance_from_the_shared_playback(self):
        values=ae.config(dict(self.values,contrast=1.7,tint_color='#20CCFF',tint_strength=65,
                             transparency=25,brightness=2.5,blend='alpha',
                             animation=dict(duration=1,canvas_scale=3,
                                            nodes=[dict(time=0,x=15,y=-10,rotation=25,scale=.8,opacity=70)])))
        data,payload=presets.encode('变换和调色','',self.clip,values)
        path=presets.store(data,payload,self.root/'transformed')
        actual=presets.poster(path,size=(23,13))
        played=ae.playback_clip(self.clip,values,self.root/'expected_playback')
        coloured=ae.colorized_clip(played,values,self.root/'expected_appearance')
        with Image.open(coloured['atlas']) as atlas:
            u,v,r,b=coloured['rects'][coloured['frames']//2]
            frame=atlas.crop((round(u*atlas.width-.5),round(v*atlas.height-.5),
                              round(r*atlas.width+.5),round(b*atlas.height+.5)))
        frame.thumbnail((23,13),Image.Resampling.LANCZOS)
        rgba=np.asarray(frame,dtype=float)/255
        rgb=rgba[:,:,:3]*values['brightness']*rgba[:,:,3:]+np.array([20,25,35])/255*(1-rgba[:,:,3:])
        expected=np.uint8(np.clip(rgb,0,1)*255)
        np.testing.assert_array_equal(np.asarray(actual),expected)

    def test_cover_leaves_preset_sources_unchanged_and_removes_temporary_cache(self):
        original=self.path.read_bytes();source=Path(self.clip['atlas']).read_bytes()
        before=set(self.path.parent.iterdir());created=[];factory=tempfile.TemporaryDirectory
        def temporary(*args,**kwargs):
            value=factory(*args,**kwargs);created.append(Path(value.name));return value
        with patch('tempfile.TemporaryDirectory',side_effect=temporary):
            presets.poster(self.path)
        self.assertEqual(self.path.read_bytes(),original)
        self.assertEqual(Path(self.clip['atlas']).read_bytes(),source)
        self.assertEqual(set(self.path.parent.iterdir()),before)
        self.assertTrue(created);self.assertTrue(all(not path.exists() for path in created))

    def test_original_non_node_cover_api_and_timing_remain_compatible(self):
        values=ae.config(dict(fps=4,blend='alpha'))
        data,payload=presets.encode('原素材','',self.clip,values)
        path=presets.store(data,payload,self.root/'plain')
        with patch.object(ae,'playback_clip') as playback:
            image=presets.poster(path,(8,4))
        playback.assert_not_called()
        self.assertEqual(image.mode,'RGB');self.assertEqual(image.size,(8,4))
        self.assertIn('1 帧 · 4 FPS · 0.25 秒',presets.summary(data))
        self.assertNotIn('节点动画',presets.description_text(data))


if __name__=='__main__':unittest.main()
