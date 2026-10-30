"""Measure every real component inference of a layered arm, without host-time costs."""
from bench.q2_execution.measured import MeasuredBackends
from bench.w1.detectors import ARMS, create_arm


class LayeredMeasuredBackends(MeasuredBackends):
    def __call__(self,lane,name,options):
        if name not in ARMS:
            return super().__call__(lane,name,options)
        component=0
        def factory(model,parameters):
            nonlocal component
            key=lane+"/"+str(component)
            component+=1
            return super(LayeredMeasuredBackends,self).__call__(key,model,parameters)
        return create_arm(name,options,detector_factory=factory)
