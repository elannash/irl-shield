"""Prepare metadata and literal argv only; never execute a benchmark or queue job."""
import argparse
import hashlib
import json
from pathlib import Path

from bench.independence import policy_metadata
from bench.metrics import validate_area_ceiling


BASE = '65891cb0b515bc0c34ec4ded89aa6a3228992cc2'
BASELINE_SHA256 = '0c1ef57d668b52d549676d842d433ed72abe07218642b70104ddc65092d18002'
INPUTS_SHA256 = '4db58cb96244791874447951b893af48f99b6bd165a59c46884a40a3c5226972'
ARMS = {
    'small1280': ('limit_side_len', 1280),
    'medium960': ('candidate', 'ppocr-v6-medium'),
    'det020': ('thresh', .2),
    'box040': ('box_thresh', .4),
    'accurate8hz': ('accurate_rate_hz', 8.),
}
POLICIES = Path(__file__).with_name('policies')
LINUX_PYTHON = '/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python'
MAC_PYTHON = '/Users/elannash/code/irl-shield-integration-run/.tmp/integration/venv/bin/python'
MAC_MIRROR = '/Users/elannash/code/irl-shield-q2-recall-bccad190'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_policies(directory=POLICIES):
    """Reject accidental combined arms before producing executable harness inputs."""
    directory = Path(directory)
    if digest(directory / 'baseline.json') != BASELINE_SHA256:
        raise ValueError('Recall baseline differs from the frozen baseline policy')
    baseline = json.loads((directory / 'baseline.json').read_text())
    policies = {'baseline': baseline}
    for arm, (key, value) in ARMS.items():
        expected = json.loads(json.dumps(baseline))
        if key == 'candidate':
            expected[key] = value
        else:
            expected['options'][key] = value
        actual = json.loads((directory / (arm + '.json')).read_text())
        if actual != expected:
            raise ValueError(f'{arm} must change only {key} to {value}')
        policies[arm] = actual
    for policy in policies.values():
        options = policy['options']
        policy_metadata(policy['candidate'], options)
        validate_area_ceiling(options['area_ceiling'], options['area_ceiling_basis'], required=True)
    return policies


def timed_argv(policy, source, output):
    """Existing clocked NVENC trial; this command does NOT measure GPU event cost."""
    options = policy['options']
    argv = [LINUX_PYTHON, '-u', '-B', '-m', 'bench.clocked_pipeline',
            '--input', str(source), '--output', str(output),
            '--candidate', policy['candidate'], '--height', '720',
            '--steady-seconds', '30', '--warmup-seconds', '10']
    for key in ('delay_seconds', 'before', 'after', 'fast_max_age', 'accurate_max_age',
                'fast_rate_hz', 'accurate_rate_hz', 'fast_width', 'accurate_width',
                'fast_candidate', 'fast_provider', 'provider', 'thresh', 'box_thresh',
                'unclip_ratio', 'limit_side_len', 'fast_limit_side_len', 'encoder',
                'motion_mode', 'motion_width', 'motion_min_response', 'padding'):
        flag = '--det-thresh' if key == 'thresh' else '--' + key.replace('_', '-')
        argv.extend([flag, str(options[key])])
    argv.append('--static-model')
    return argv


def prepare_plan(root, inputs, directory=POLICIES):
    """Bind five opt-in arms to the exact spent tune manifest, without reading pixels."""
    root, inputs, directory = Path(root), Path(inputs), Path(directory)
    if digest(inputs) != INPUTS_SHA256:
        raise ValueError('Recall requires the exact frozen tune input manifest')
    policies = load_policies(directory)
    data = json.loads(inputs.read_text())
    # The existing harness owns corpus validation, pixel verification and sealing.
    runs = {}
    for arm, policy in policies.items():
        render, grade = [], []
        for row in data['clips']:
            label = row['clip'] + ('-synthetic' if row['synthetic_variant'] else '-natural')
            relative = Path('out/q2-recall') / arm / label
            argv = [LINUX_PYTHON, '-u', '-B', '-m', 'bench.quality_bundle',
                    '--root', str(root), '--lock-root', '/home/elan/code/irl-shield',
                    'render', '--inputs', str(inputs), '--config', str(directory / (arm + '.json')),
                    '--directory', str(root / relative), '--clip', row['clip']]
            if row['synthetic_variant']:
                argv.append('--synthetic')
            render.append(argv)
            grade.append([MAC_PYTHON, '-u', '-B', '-m', 'bench.quality_bundle',
                          '--root', MAC_MIRROR, '--lock-root', '/Users/elannash/code/irl-shield',
                          'grade', '--directory', str(Path(MAC_MIRROR) / relative),
                          '--cache', '/Users/elannash/code/irl-shield-q-quality/out/judge-cache'])
        source = next(row['source'] for row in data['clips'] if not row['synthetic_variant'])
        runs[arm] = {
            'config_sha256': digest(directory / (arm + '.json')),
            'detector_metadata': policy_metadata(policy['candidate'], policy['options']),
            'render_argv': render, 'grade_argv': grade,
            'aggregate_argv': [MAC_PYTHON, '-u', '-B', '-m', 'bench.quality_bundle',
                               '--root', MAC_MIRROR, 'aggregate',
                               '--directory', str(Path(MAC_MIRROR) / 'out/q2-recall' / arm),
                               '--run-id', 'q2-recall-' + arm],
            'clocked_argv': [timed_argv(policy, source, root / 'out/q2-recall-perf' / arm / f'rep-{n}.mp4')
                             for n in range(1, 6)],
            'gpu_event_argv': None,
            'gpu_event_blocker': 'No public known-userstream seam in detector_for/_session; see README timing contract',
            'quality': None, 'gpu_ms_per_source_frame': None, 'promotable': False,
        }
    return {'status': 'HELD', 'base': BASE, 'input_manifest_sha256': digest(inputs),
            'requires_root_relay': ['PHONE_TEST_DONE', 'GPU_RELEASED', 'V2_FROZEN manifestSHA', 'active EX queue'],
            'commands_executed': False, 'runs': runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = prepare_plan(args.root, args.inputs)
    with args.output.open('x') as stream:
        stream.write(json.dumps(plan, indent=2) + '\n')


if __name__ == '__main__':
    main()
