"""Adversarial checks for the instruction-only dependency pack; no upstream execution."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools.check_skill_pack import check

ROOT = Path(__file__).resolve().parents[1]


class SkillPackTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / '.implementation/tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / '.claude/skills', self.root / '.claude/skills')
        shutil.copy2(ROOT / '.claude/skill-pack.json', self.root / '.claude/skill-pack.json')
        for name in ('prompts/START_MODERNIZATION.md', 'docs/TECHNICAL_REFERENCE.md'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, path)
        self.manifest_path = self.root / '.claude/skill-pack.json'
        self.manifest = json.loads(self.manifest_path.read_text())

    def save(self):
        self.manifest_path.write_text(json.dumps(self.manifest))

    def corrupt_text(self, text, name='superpowers'):
        package = next(p for p in self.manifest['packages'] if p['name'] == name)
        record = next(f for f in package['files'] if f['path'].endswith('/SKILL.md'))
        path = self.root / record['path']
        path.write_text(text)
        record['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        record['bytes'] = path.stat().st_size
        package['installed_bytes'] = sum(f['bytes'] for f in package['files'])
        self.save()

    def assertRejected(self, message):
        result = check(self.root)
        self.assertFalse(result['passed'], result)
        self.assertTrue(any(message in item for item in result['issues']), result)

    def test_current_pack_passes_with_exact_origins_and_retained_skills(self):
        result = check(self.root)
        self.assertTrue(result['passed'], result)
        self.assertEqual(15, result['package_count'])
        self.assertEqual(19, result['skill_count'])
        self.assertEqual(29, result['file_count'])

    def test_missing_requested_origin_rejected(self):
        self.manifest['packages'].pop(); self.save()
        self.assertRejected('requested package set')

    def test_duplicate_package_rejected(self):
        self.manifest['packages'].append(copy.deepcopy(self.manifest['packages'][0])); self.save()
        self.assertRejected('duplicate package')

    def test_wrong_origin_rejected(self):
        self.manifest['packages'][0]['requested_origin'] = 'untrusted/replacement'; self.save()
        self.assertRejected('origin')

    def test_branch_instead_of_immutable_commit_rejected(self):
        self.manifest['packages'][0]['upstream_commit'] = 'main'; self.save()
        self.assertRejected('commit')

    def test_unpinned_source_url_rejected(self):
        p = self.manifest['packages'][0]
        p['source']['url'] = p['source']['url'].replace(p['upstream_commit'], 'main'); self.save()
        self.assertRejected('pinned source URL')

    def test_changed_installed_content_rejected(self):
        p = self.root / '.claude/skills/superpowers/SKILL.md'
        p.write_text(p.read_text() + '\nChanged instructions.\n')
        self.assertRejected('hash/size')

    def test_script_payload_rejected_even_unlisted(self):
        (self.root / '.claude/skills/headroom/run.py').write_text('raise RuntimeError("never run")')
        self.assertRejected('unregistered or non-Markdown')

    def test_unexpected_runtime_directory_rejected(self):
        (self.root / '.claude/skills/ponytail/hooks').mkdir()
        self.assertRejected('unexpected directory')

    def test_executable_markdown_rejected(self):
        (self.root / '.claude/skills/impeccable/SKILL.md').chmod(0o755)
        self.assertRejected('executable')

    def test_symlink_file_rejected_without_reading_target(self):
        p = self.root / '.claude/skills/superpowers/SKILL.md'
        p.unlink(); p.symlink_to(self.root / 'prompts/START_MODERNIZATION.md')
        self.assertRejected('link')

    def test_directory_symlink_rejected_without_reading_any_target_content(self):
        package = self.root / '.claude/skills/superpowers'
        target = self.root / 'external'
        shutil.move(str(package), str(target))
        package.symlink_to(target, target_is_directory=True)
        original = Path.read_bytes
        def guarded(path):
            if package in path.parents:
                raise AssertionError('Read through linked directory')
            return original(path)
        with patch.object(Path, 'read_bytes', guarded):
            self.assertRejected('link')

    def test_path_traversal_in_manifest_rejected(self):
        self.manifest['packages'][0]['files'][0]['path'] = '.claude/skills/superpowers/../../../outside.md'; self.save()
        self.assertRejected('unsafe file path')

    def test_runtime_flag_rejected(self):
        self.manifest['runtime_installed'] = True; self.save()
        self.assertRejected('runtime')

    def test_permission_grant_rejected(self):
        self.manifest['permission_grants'] = ['Bash(*)']; self.save()
        self.assertRejected('permissions')

    def test_skill_tool_grant_rejected_after_hash_refresh(self):
        p = self.root / '.claude/skills/superpowers/SKILL.md'
        self.corrupt_text(p.read_text().replace('---\n\n', 'allowed-tools: Bash\n---\n\n', 1))
        self.assertRejected('frontmatter')

    def test_missing_local_reference_rejected_after_hash_refresh(self):
        p = self.root / '.claude/skills/superpowers/SKILL.md'
        self.corrupt_text(p.read_text() + '\n[Missing instructions](missing.md)\n')
        self.assertRejected('broken or unsafe local reference')

    def test_description_budget_rejected_after_hash_refresh(self):
        p = self.root / '.claude/skills/superpowers/SKILL.md'
        lines = p.read_text().splitlines()
        lines[2] = 'description: ' + 'a' * 257
        self.corrupt_text('\n'.join(lines) + '\n')
        self.assertRejected('description')

    def test_independent_adapter_cannot_claim_redistributed_unlicensed_text(self):
        p = next(p for p in self.manifest['packages'] if p['name'] == 'karpathy-guidelines')
        p['license']['redistributed_upstream_text'] = True; self.save()
        self.assertRejected('unlicensed')

    def test_headroom_cannot_claim_actual_upstream_skill(self):
        p = next(p for p in self.manifest['packages'] if p['name'] == 'headroom')
        p['mode'] = 'adapted_upstream_subset'; self.save()
        self.assertRejected('adapter')

    def test_retained_mainframe_skill_required(self):
        shutil.rmtree(self.root / '.claude/skills/mainframe-semantics')
        self.assertRejected('retained skill')

    def test_license_notice_hash_verified(self):
        (self.root / '.claude/skills/ecc/LICENSE.md').write_text('MIT')
        self.assertRejected('hash/size')

    def test_unknown_manifest_activation_field_rejected(self):
        self.manifest['hooks'] = {'startup': 'untrusted.exe'}; self.save()
        self.assertRejected('unknown manifest field')

    def test_retained_directory_cannot_hide_new_runtime(self):
        (self.root / '.claude/skills/mainframe-target/run.ps1').write_text('Write-Output unsafe')
        self.assertRejected('retained skill payload')

    def test_retained_skill_link_rejected(self):
        p = self.root / '.claude/skills/mainframe-target/extra.md'
        p.symlink_to(self.root / 'prompts/START_MODERNIZATION.md')
        self.assertRejected('retained skill payload')

    def test_duplicate_json_keys_rejected(self):
        self.manifest_path.write_text('{"schema_version":1,"schema_version":1}')
        self.assertRejected('duplicate JSON key')

    def test_extra_skill_not_silently_installed(self):
        (self.root / '.claude/skills/extra').mkdir()
        (self.root / '.claude/skills/extra/SKILL.md').write_text('extra')
        self.assertRejected('skill directory set')


if __name__ == '__main__':
    unittest.main()
