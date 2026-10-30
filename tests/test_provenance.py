import copy
import unittest

from bench.provenance import validate_sustained


class SustainedReceipt(unittest.TestCase):
    def receipt(self):
        results={}
        for label,height,pace in [('720-saturated',720,False),('720-paced',720,True),('1080-saturated',1080,False)]:
            seconds=30 if pace else 20
            results[label]={'frames':900,'resolution':[height*16//9,height],'source_fps':30,
                            'pace':pace,'pipeline_sha256':'pipeline','seconds':seconds,'fps':900/seconds,
                            'realtime_added_latency_seconds':{'p50':.2,'p95':.5}}
        return {'candidate':'detector','options':{'stride':3},'source_sha256':'source',
                'pipeline_sha256':'pipeline','seconds':30,'results':results}

    def test_only_current_full_workload_is_accepted(self):
        original=self.receipt()
        validate_sustained(original,'detector',{'stride':3},'source','pipeline')
        mutations=[('old-code',lambda c:c.update(pipeline_sha256='old')),
                   ('easy-source',lambda c:c.update(source_sha256='easier')),
                   ('too-few-frames',lambda c:c['results']['720-saturated'].update(frames=90)),
                   ('wrong-resolution',lambda c:c['results']['1080-saturated'].update(resolution=[1280,720])),
                   ('unpaced',lambda c:c['results']['720-paced'].update(pace=False)),
                   ('short-clock',lambda c:c['results']['720-paced'].update(seconds=3,fps=300)),
                   ('inconsistent-fps',lambda c:c['results']['720-saturated'].update(fps=300)),
                   ('nonfinite-latency',lambda c:c['results']['720-paced']['realtime_added_latency_seconds'].update(p95=float('nan')))]
        for name,mutate in mutations:
            with self.subTest(name=name):
                card=copy.deepcopy(original)
                mutate(card)
                with self.assertRaises(ValueError):
                    validate_sustained(card,'detector',{'stride':3},'source','pipeline')
