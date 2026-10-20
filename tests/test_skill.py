"""The Claude Code skill in skills/ follows the Agent Skills format and the
writing rules of tools/check_skills.py in the sibling HousingWizard repo:
frontmatter name matches the folder, description 1 to 1024 characters, SKILL.md
under 500 lines, every mentioned references/ file exists, English only, no
emoji, no em dash. Also checks that the commands it tells an agent to run exist."""

import glob
import os
import re
import unittest

from geo import cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")))
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CJK = re.compile("[%s]" % "".join("%s-%s" % (chr(a), chr(b)) for a, b in (
    (0x3000, 0x303f), (0x3040, 0x30ff), (0x3400, 0x4dbf), (0x4e00, 0x9fff), (0xac00, 0xd7af), (0xff00, 0xffef))))
EMOJI = re.compile("[%s-%s%s-%s]" % (chr(0x1F300), chr(0x1FAFF), chr(0x2600), chr(0x27BF)))
EM_DASH = re.compile(chr(0x2014))


def frontmatter(text):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    fm = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


class SkillFormat(unittest.TestCase):
    def test_there_is_a_skill(self):
        self.assertEqual([os.path.basename(os.path.dirname(p)) for p in SKILLS], ["aceseo"])

    def test_frontmatter_and_size(self):
        for path in SKILLS:
            folder = os.path.basename(os.path.dirname(path))
            with open(path, encoding="utf-8") as f:
                text = f.read()
            fm = frontmatter(text)
            self.assertIsNotNone(fm, folder)
            self.assertEqual(fm.get("name"), folder)
            self.assertTrue(NAME.match(folder) and len(folder) <= 64)
            self.assertTrue(1 <= len(fm.get("description", "")) <= 1024)
            self.assertLess(text.count("\n"), 500)

    def test_mentioned_files_exist(self):
        for path in SKILLS:
            with open(path, encoding="utf-8") as f:
                text = f.read()
            refs = re.findall(r"`((?:references|assets|scripts)/[^`\s]+)`", text)
            self.assertTrue(refs)
            for ref in refs:
                self.assertTrue(os.path.exists(os.path.join(os.path.dirname(path), ref)), ref)

    def test_writing_rules(self):
        for path in glob.glob(os.path.join(ROOT, "skills", "**", "*.md"), recursive=True):
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for label, pat in (("CJK text", CJK), ("emoji", EMOJI), ("em dash", EM_DASH)):
                self.assertIsNone(pat.search(text), "%s: %s" % (os.path.relpath(path, ROOT), label))

    def test_repo_paths_and_commands_exist(self):
        parser = cli._parser()
        subs = next(a for a in parser._actions if a.dest == "cmd").choices
        for path in glob.glob(os.path.join(ROOT, "skills", "**", "*.md"), recursive=True):
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for cmd in re.findall(r"python3 -m geo\.cli ([a-z-]+)", text):
                self.assertIn(cmd, subs, path)
            for rel in re.findall(r"`((?:geo|step0|examples|design|tests)/[^`\s*<]+)`", text):
                self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), "%s: %s" % (path, rel))


if __name__ == "__main__":
    unittest.main()
