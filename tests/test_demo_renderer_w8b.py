"""Synthetic W8b contracts; native encode, branding and visual approval stay external."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from tools.demo_renderer.source import build, camera_box, compose, frame_geometry, load_scene_plan, sha256
from tools.demo_renderer.sender import source_manifest


class MosaicSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.cache = cls.root / 'cache'
        cls.cache.mkdir()
        repository = Path(__file__).resolve().parents[1]
        cls.recipe = json.loads((repository / 'fixtures/demo-renderer/w8b/scene-plan.json').read_text())
        for asset, color in zip(cls.recipe['assets'], ('red', 'lime', 'blue', 'yellow')):
            path = cls.cache / asset['file']
            image = Image.new('RGB', (1536, 1024), color)
            if asset['id'] == 'corner':
                image.putpixel((540, 696), (91, 92, 93))
            image.save(path)
            asset['sha256'] = sha256(path)
        for filename, key in (('ATTRIBUTION.json', 'attribution_sha256'), ('prompts.json', 'prompts_sha256')):
            path = cls.root / filename
            path.write_text('{"synthetic":true}\n')
            cls.recipe[key] = sha256(path)

    def plan(self, recipe=None):
        path = self.root / 'scene-plan.json'
        path.write_text(json.dumps(self.recipe if recipe is None else recipe))
        return load_scene_plan(path, asset_base=self.cache)

    def test_camera_support_clock_length_and_continuity_through_all_joins(self):
        plan = self.plan()
        self.assertEqual(camera_box(0, scene_plan=plan), (32, 264, 1376, 1020))
        self.assertEqual(camera_box(6299, scene_plan=plan), (4448, 50, 5728, 770))
        previous = camera_box(0, scene_plan=plan)
        for index in range(1, 6300):
            box = camera_box(index, scene_plan=plan)
            left, top, right, bottom = box
            self.assertTrue(0 <= left < right <= 5760 and 0 <= top < bottom <= 1024)
            self.assertGreater(left, previous[0])
            self.assertLess(right - left, previous[2] - previous[0])
            self.assertGreaterEqual(right - left, 1280)
            self.assertAlmostEqual((right - left) * 9, (bottom - top) * 16)
            for old, new in zip(previous, box):
                self.assertLess(abs(new - old), 2)
            previous = box
        for invalid in (-1, 6300, True, 1.0):
            with self.subTest(index=invalid), self.assertRaises(ValueError):
                camera_box(invalid, scene_plan=plan)

    def test_approximate_sign_regions_have_three_second_full_view_windows(self):
        plan = self.plan()
        assets = {asset['id']: asset for asset in plan['assets']}
        for region in plan['readability_regions']:
            with self.subTest(label=region['label']):
                x, y = assets[region['asset']]['origin']
                a, b, c, d = region['bounds']
                start, stop = region['full_view_frames']
                self.assertGreaterEqual(stop - start, 60)
                for index in range(start, stop):
                    left, top, right, bottom = camera_box(index, scene_plan=plan)
                    self.assertTrue(left <= x+a < x+c <= right and top <= y+b < y+d <= bottom)
                for join in plan['joins']:
                    feather_left, feather_right = join['feather']
                    self.assertTrue(x+c <= feather_left or x+a >= feather_right)
                if region['asset'] in ('homes', 'car'):
                    self.assertLessEqual(camera_box(0, scene_plan=plan)[2], x+a)
                    self.assertGreaterEqual(camera_box(6299, scene_plan=plan)[0], x+c)
        # This is rectangle feasibility, not an assertion about generated glyph pixels.

    def test_each_plate_has_a_declared_label_enter_through_a_frame_edge(self):
        plan = self.plan()
        opening = camera_box(0, scene_plan=plan)
        assets = {asset['id']: asset for asset in plan['assets']}
        entries = {entry['asset']: entry for entry in plan['entry_reference_regions']}
        self.assertEqual(set(entries), {'shops', 'homes', 'car', 'corner'})
        for identity, entry in entries.items():
            region = next(r for r in plan['readability_regions']
                          if r['asset'] == identity and r['label'] == entry['label'])
            x, y = assets[identity]['origin']
            a, b, c, d = region['bounds']
            if entry['edge'] == 'top':
                self.assertLessEqual(y+d, opening[1])
            else:
                self.assertLessEqual(opening[2], x+a)
            start, stop = region['full_view_frames']
            self.assertGreaterEqual(stop-start, 60)
            for index in (start, stop-1):
                left, top, right, bottom = camera_box(index, scene_plan=plan)
                self.assertTrue(left <= x+a < x+c <= right and top <= y+b < y+d <= bottom)

    def test_copied_poles_span_every_visible_join_and_leave_label_windows_clear(self):
        plan = self.plan()
        for pole in plan['foreground_poles']:
            dx, dy = pole['translation']
            visible_count = 0
            for index in range(6300):
                left, top, right, bottom = camera_box(index, scene_plan=plan)
                if right > dx+512 and left < dx+553:
                    visible_count += 1
                    self.assertTrue(240+dy <= top < bottom <= 1024+dy)
            self.assertGreater(visible_count, 0)
            for region in plan['readability_regions']:
                origin = next(a['origin'][0] for a in plan['assets'] if a['id'] == region['asset'])
                a, _, c, _ = region['bounds']
                self.assertTrue(origin+c <= dx+512 or origin+a >= dx+553)

    def test_composition_owns_spatial_feathers_and_never_draws_lettering(self):
        plan = self.plan()
        with patch('PIL.ImageDraw.Draw', side_effect=AssertionError('W8b painted lettering')):
            scene = compose(scene_plan=plan)
        self.assertEqual(scene.size, (5760, 1024))
        for y in (50, 769):
            for x, color in ((100, (255, 0, 0)), (1480, (255, 0, 0)),
                             (1520, (255, 255, 0)), (1545, (0, 255, 0)),
                             (2900, (0, 255, 0)), (2928, (255, 255, 0)),
                             (2950, (0, 0, 255)), (4336, (255, 255, 0)),
                             (5730, (255, 255, 0))):
                with self.subTest(pixel=(x, y)):
                    self.assertEqual(scene.getpixel((x, y)), color)
        for point in ((1520,500), (2928,500), (4336,500)):
            self.assertEqual(scene.getpixel(point), (91, 92, 93))

    def test_geometry_exports_actual_crop_map_but_no_native_or_mask_attestation(self):
        plan = self.plan()
        opening = frame_geometry(0, plan)
        self.assertEqual(opening['crop'], [32, 264, 1376, 1020])
        shops = opening['assets'][0]
        self.assertEqual(shops['plate_to_output'][0], [20/21, 0, -640/21])
        final = frame_geometry(6299, plan)
        corner = final['assets'][3]
        self.assertEqual(corner['plate_to_output'], [[1, 0, -224], [0, 1, -50]])
        self.assertEqual(corner['output_to_plate'], [[1, 0, 224], [0, 1, 50]])
        sign = next(row for row in final['references'] if row['name'] == 'NERALIN LANE blade')
        self.assertEqual(sign['reference_quad'], [[548,102], [704,102], [704,214], [548,214]])
        self.assertEqual(sign['output_quad'], [[324,52], [480,52], [480,164], [324,164]])
        self.assertTrue(sign['declared_rectangle_inside_crop'])
        self.assertIsNone(sign['actual_mask_coverage'])
        self.assertEqual(final['foreground_layers'][0]['source_box'], [504,240,560,1024])
        self.assertEqual(final['foreground_layers'][0]['source_to_output'],
                         [[1,0,-3468], [0,1,-246]])
        self.assertEqual(len(plan['per_plate_samples']), 4)
        self.assertTrue(all(len(roster) == 12 for roster in plan['per_plate_samples'].values()))
        self.assertEqual(plan['raw_samples'], sorted({i for roster in plan['per_plate_samples'].values() for i in roster}))

    def test_recipe_refuses_hash_paths_dimensions_geometry_and_provenance_errors(self):
        cases = []
        for filename in ('../shops-v1.png', '/tmp/shops-v1.png', 'cache\\shops-v1.png'):
            recipe = deepcopy(self.recipe)
            recipe['assets'][0]['file'] = filename
            cases.append(('asset path', recipe))
        for name, edit in (
                ('asset seal', lambda p: p['assets'][0].update(sha256='0' * 64)),
                ('asset geometry', lambda p: p['assets'][1].update(origin=[1536, 0])),
                ('camera outside', lambda p: p['camera'].update(left=[32, 4600])),
                ('without upsampling', lambda p: p['camera'].update(width=[1344, 1152])),
                ('static feather', lambda p: p['joins'][0].update(feather=[1440, 1540])),
                ('cover join', lambda p: p['foreground_poles'][0].update(translation=[1000,-196])),
                ('ends inside', lambda p: p['foreground_poles'][0].update(translation=[980,-250])),
                ('provenance seal', lambda p: p.update(prompts_sha256='0' * 64)),
                ('per-plate sample', lambda p: p['per_plate_samples']['shops'].pop()),
                ('reference region', lambda p: p['readability_regions'][0].update(bounds=[-1,55,555,258])),
                ('sample roster', lambda p: p.update(raw_samples=[0, 6299]))):
            recipe = deepcopy(self.recipe)
            edit(recipe)
            cases.append((name, recipe))
        for message, recipe in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.plan(recipe)
        with self.assertRaisesRegex(ValueError, 'directory missing'):
            load_scene_plan(self.root / 'scene-plan.json', asset_base=self.root / 'absent')
        recipe = deepcopy(self.recipe)
        recipe['assets'][0]['file'] = 'missing.png'
        with self.assertRaises(FileNotFoundError):
            self.plan(recipe)
        link = self.cache / 'linked.png'
        link.symlink_to(self.cache / 'shops-v1.png')
        try:
            recipe = deepcopy(self.recipe)
            recipe['assets'][0]['file'] = 'linked.png'
            with self.assertRaisesRegex(ValueError, 'path escapes'):
                self.plan(recipe)
        finally:
            link.unlink()
        original = (self.cache / 'shops-v1.png').read_bytes()
        try:
            small = self.cache / 'shops-v1.png'
            Image.new('RGB', (20, 20)).save(small)
            recipe = deepcopy(self.recipe)
            recipe['assets'][0]['sha256'] = sha256(small)
            with self.assertRaisesRegex(ValueError, 'PNG dimensions'):
                self.plan(recipe)
        finally:
            (self.cache / 'shops-v1.png').write_bytes(original)

    def test_missing_or_changed_cached_asset_fails_without_native_import_or_generation(self):
        recipe = deepcopy(self.recipe)
        recipe['assets'][0]['sha256'] = '0' * 64
        path = self.root / 'bad-plan.json'
        path.write_text(json.dumps(recipe))
        with patch('tools.demo_renderer.source.inherited_exclusive'), patch.dict('sys.modules', {'av': None}):
            with self.assertRaisesRegex(ValueError, 'asset seal'):
                build(self.root / 'output', scene_plan=path, asset_base=self.cache)
            with self.assertRaisesRegex(ValueError, 'paired'):
                build(self.root / 'output', scene_plan=path)
            with self.assertRaisesRegex(ValueError, 'directory missing'):
                build(self.root / 'output', scene_plan=path, asset_base=self.root / 'missing')
        self.assertFalse((self.root / 'output').exists())

    def test_default_legacy_camera_and_composition_still_use_original_route(self):
        self.assertEqual(camera_box(0), (36, 40, 1536, 883.75))
        last = camera_box(6299)
        self.assertAlmostEqual(last[0], 216)
        self.assertAlmostEqual(last[1], 40)
        self.assertAlmostEqual(last[2], 1476)
        self.assertAlmostEqual(last[3], 748.75)
        with patch('tools.demo_renderer.source.compose_mosaic', side_effect=AssertionError('legacy changed')):
            scene = compose()
        self.assertEqual(scene.size, (1920, 1080))
        self.assertEqual(scene.getpixel((300, 600)), (24, 60, 52))
        self.assertEqual(scene.getpixel((220, 445)), (243, 242, 238))

    def test_opt_in_receipt_remains_compatible_with_sender_pts_and_hash_boundary(self):
        root = self.root / 'transport'
        root.mkdir(exist_ok=True)
        video = root / 'source.mp4'
        video.write_bytes(b'synthetic-envelope-only-not-video')
        manifest = {'schema': 'irl-shield-w8-source-v1', 'video': 'source.mp4',
                    'fps': 30, 'seconds': 210, 'video_sha256': sha256(video),
                    'frames': [{'source_index': i, 'pts': str(Fraction(i, 30))} for i in range(6300)],
                    'composition': {'recipe': self.recipe, 'native_verified': None}}
        path = root / 'source.json'
        path.write_text(json.dumps(manifest))
        self.assertEqual(source_manifest(path)[0], video)
        self.assertEqual(source_manifest(path)[1]['frames'][6299]['pts'], '6299/30')
        for name in ('pts', 'source_index', 'video_sha256', 'frames'):
            broken = deepcopy(manifest)
            if name == 'pts':
                broken['frames'][1]['pts'] = '2/30'
            elif name == 'source_index':
                broken['frames'][1]['source_index'] = 2
            elif name == 'frames':
                broken['frames'].pop()
            else:
                broken[name] = '0' * 64
            path.write_text(json.dumps(broken))
            with self.subTest(corruption=name), self.assertRaises(ValueError):
                source_manifest(path)


if __name__ == '__main__':
    unittest.main()
