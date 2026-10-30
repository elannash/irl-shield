"""Explicit render factories with relocatable, sealed source provenance."""
from dataclasses import dataclass, field
import hashlib
import inspect
import json
import math
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_identity(root, identity):
    if identity is None:
        return
    for source in identity['sources']:
        name = Path(source['path'])
        path = Path(root) / name
        if name.is_absolute() or not path.resolve().is_relative_to(Path(root).resolve()):
            raise ValueError('Execution adapter source escapes root')
        if sha256(path) != source['sha256']:
            raise ValueError('Execution adapter source changed: ' + str(name))


@dataclass(frozen=True)
class RenderFactories:
    renderer: object = None
    motion: object = None
    parameters: dict = field(default_factory=dict)

    def identity(self, root):
        sources, factories = {}, {}
        for name, factory in (('renderer', self.renderer), ('motion', self.motion)):
            if factory is None:
                continue
            if not inspect.isfunction(factory) or factory.__closure__ or factory.__name__ == '<lambda>':
                raise ValueError('Sealed factories must be named module functions without closures')
            source = Path(inspect.getsourcefile(factory)).resolve()
            relative = str(source.relative_to(Path(root).resolve()))
            sources[relative] = {'path': relative, 'sha256': sha256(source)}
            factories[name] = factory.__module__ + '.' + factory.__qualname__
        return {'factories': factories, 'parameters': json.loads(json.dumps(self.parameters, allow_nan=False)),
                'sources': [sources[key] for key in sorted(sources)]}

    def build(self, fps, options):
        return {name: factory(fps, dict(options), dict(self.parameters))
                for name, factory in (('renderer', self.renderer), ('motion', self.motion)) if factory is not None}


def padding_budget_renderer(fps, options, parameters):
    from shield.mask_precision import PaddingBudgetRenderer
    if options.get('badge') or options.get('style', 'opaque') != 'opaque':
        raise ValueError('Union budget adapter supports opaque masking without badge only')
    return PaddingBudgetRenderer(max_mask_fraction=parameters['max_mask_fraction'],
                                 padding=options.get('padding', .3))


def flow_motion(fps, options, parameters):
    from shield.motion import MotionHistory
    delay = float(options.get('delay_seconds', 1.))
    if not math.isfinite(delay) or not 0 <= delay <= (3. if parameters.get('diagnostic_delay') is True else 1.):
        raise ValueError('Flow factory supports the existing D<=1 offline validator only')
    return MotionHistory(max_frames=max(120, math.ceil(fps * delay) + options.get('before', 6) + 4),
                         analysis_width=options.get('motion_width', 320), mode=options.get('motion_mode','flow'),
                         phase_min_response=options.get('motion_min_response', .5),
                         max_projection_frames=math.floor(delay * fps))


def factories_for(config, options):
    if set(config) - {'renderer', 'max_mask_fraction', 'diagnostic_delay'}:
        raise ValueError('Unknown Q2 execution adapter option')
    renderer = None
    if 'renderer' in config or 'max_mask_fraction' in config:
        if config.get('renderer') != 'union-budget' or 'max_mask_fraction' not in config:
            raise ValueError('Union budget requires an explicit renderer and mask fraction')
        renderer = padding_budget_renderer
    motion = flow_motion if options.get('motion_mode') in {'flow','box-flow'} else None
    return RenderFactories(renderer, motion, dict(config)) if renderer or motion or config else None


def factory_identity(factory, root):
    target = factory if inspect.isfunction(factory) else type(factory)
    source = Path(inspect.getsourcefile(target)).resolve()
    relative = str(source.relative_to(Path(root).resolve()))
    return {'factory': target.__module__ + '.' + target.__qualname__,
            'sources': [{'path': relative, 'sha256': sha256(source)}]}
