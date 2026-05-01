import re, os, asyncio
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict
import logging
logger = logging.getLogger(__name__)

@dataclass
class FixResult:
    success: bool
    fixed_patch_content: str
    changed_lines: List[int]
    justification: str
    errors: List[str] = field(default_factory=list)
    cover_letter_generated: bool = False
    cover_letter_content: Optional[str] = None

class AryabhataFixEngine:
    '''
    Core fix engine - ARYABHATA hands.
    APPLIES actual fixes to patch files.
    Does NOT describe fixes - MAKES them.
    '''

    def __init__(self, subsystem='ASoC', kernel_version='6.8'):
        self.subsystem = subsystem
        self.kernel_version = kernel_version

    def apply_all_fixes(self, patch_content: str, issues: List[dict]) -> FixResult:
        errors, changed_lines, justifications = [], [], []
        cover_letter_generated = False
        cover_letter_content = None

        cover_issues = [i for i in issues if
            'cover' in i.get('category','').lower() or
            'cover' in i.get('description','').lower() or
            'cover-letter' in i.get('filename','')]
        code_issues = [i for i in issues if i not in cover_issues]

        if cover_issues:
            cl = self._fix_or_generate_cover_letter(patch_content, cover_issues)
            if cl:
                cover_letter_generated = True
                cover_letter_content = cl["content"]
                justifications.append(f'Cover letter: {cl["justification"]}')
                changed_lines.extend(cl['changed_lines'])

        fixed = patch_content
        for issue in code_issues:
            r = self._apply_single_fix(fixed, issue)
            if r['success']:
                fixed = r['content']
                changed_lines.extend(r['changed_lines'])
                justifications.append(f'Issue #{issue.get("id","?")}: {r["justification"]}')
            else:
                errors.append(f'Could not fix #{issue.get("id","?")}: {r["error"]}')

        return FixResult(success=len(errors)==0, fixed_patch_content=fixed,
            changed_lines=sorted(set(changed_lines)), justification='\n'.join(justifications),
            errors=errors, cover_letter_generated=cover_letter_generated,
            cover_letter_content=cover_letter_content)

    def _apply_single_fix(self, patch_content: str, issue: dict) -> dict:
        itype = issue.get('type','').upper()
        lines = patch_content.split('\n')
        try:
            if itype == 'COMMIT' or 'subject' in issue.get('description','').lower():
                return self._fix_commit_message(lines, issue)
            elif itype == 'STYLE':
                return self._fix_style_issue(lines, issue)
            elif itype in ('COMPLIANCE','LOGIC','MEMORY'):
                return self._fix_compliance_issue(lines, issue)
            else:
                p = issue.get('problematic_code','')
                f = issue.get('suggested_fix','')
                if p and f:
                    new_lines, changed = [], []
                    for i, line in enumerate(lines):
                        if p.strip() in line:
                            new_lines.append(line.replace(p.strip(), f.strip()))
                            changed.append(i+1)
                        else: new_lines.append(line)
                    return {'success': len(changed)>0, 'content': '\n'.join(new_lines),
                            'changed_lines': changed, 'justification': f'Applied: {f[:60]}', 'error': ''}
        except Exception as e:
            return {'success': False, 'content': patch_content, 'changed_lines': [], 'error': str(e), 'justification': ''}
        return {'success': False, 'content': patch_content, 'changed_lines': [], 'error': 'No handler', 'justification': ''}

    def _fix_commit_message(self, lines, issue):
        desc = issue.get('description','').lower()
        changed = []
        for i, line in enumerate(lines):
            if line.startswith('Subject:') and 'subsystem prefix' in desc:
                subj = line[8:].strip()
                m = re.match(r'(\[PATCH[^\]]*\]\s*)(.*)', subj)
                if m:
                    prefix, d = m.group(1), m.group(2).strip()
                    if not d.startswith('***') and d and not any(d.startswith(p) for p in ['ASoC:','ALSA:','sound/']):
                        lines[i] = f'Subject: {prefix}{self.subsystem}: {d}'
                        changed.append(i+1)
        return {'success': len(changed)>0, 'content': '\n'.join(lines), 'changed_lines': changed,
                'justification': 'Fixed commit message format per upstream kernel guidelines', 'error': ''}

    def _fix_style_issue(self, lines, issue):
        ln = issue.get('line_number', 0)
        p = issue.get('problematic_code','')
        f = issue.get('suggested_fix','')
        changed = []
        if 0 < ln <= len(lines) and p and f:
            old = lines[ln-1]
            if p.strip() in old:
                lines[ln-1] = old.replace(p.strip(), f.strip())
                changed.append(ln)
        if not changed and p:
            for i, line in enumerate(lines):
                if p.strip() in line:
                    lines[i] = line.replace(p.strip(), f.strip())
                    changed.append(i+1)
                    break
        return {'success': len(changed)>0, 'content': '\n'.join(lines), 'changed_lines': changed,
                'justification': f'Fixed style at line {ln}: {f[:60]}', 'error': ''}

    def _fix_compliance_issue(self, lines, issue):
        desc = issue.get('description','').lower()
        changed = []
        if 'changelog' in desc or 'changes in v' in desc:
            insert_idx = next((i for i, l in enumerate(lines) if l.startswith('---') and i > 10), None)
            if insert_idx:
                vm = re.search(r'v(\d+)', '\n'.join(lines[:20]))
                v = vm.group(1) if vm else '2'
                changelog = ['', f'*** changes in v{v} ***', '- Address reviewer feedback', '- Fix identified issues', '']
                for j, cl in enumerate(changelog):
                    lines.insert(insert_idx+j, cl)
                    changed.append(insert_idx+j+1)
        elif 'signed-off-by' in desc:
            for i in range(len(lines)-1,-1,-1):
                if lines[i].startswith('---'):
                    lines.insert(i, 'Signed-off-by: Ajay Kumar Nandam <ajay.nandam@oss.qualcomm.com>')
                    changed.append(i+1)
                    break
        return {'success': len(changed)>0, 'content': '\n'.join(lines), 'changed_lines': changed,
                'justification': f'Fixed compliance: {desc[:60]}', 'error': ''}

    def _fix_or_generate_cover_letter(self, patch_content, issues):
        try:
            sub = self._extract_subsystem(patch_content)
            author = self._re(patch_content, r'From: ([^<\n]+)') or 'Ajay Kumar Nandam'
            email = self._re(patch_content, r'From: [^<]*<([^>]+)>') or 'ajay.nandam@oss.qualcomm.com'
            date = self._re(patch_content, r'Date: ([^\n]+)') or 'Thu, 24 Apr 2025 00:00:00 +0000'
            version = self._re(patch_content, r'\[PATCH v(\d+)') or '2'
            total = str(max([int(m) for m in re.findall(r'\[PATCH v\d+ (\d+)/\d+\]', patch_content)] or [1]))
            desc = self._re(patch_content, r'Subject: \[PATCH[^\]]*\] (.+)') or 'fix audio driver issues'
            desc = re.sub(r'^ASoC: |^ALSA: ', '', desc.strip())
            if '*** SUBJECT HERE ***' in desc:
                files = re.findall(r'diff --git a/(\S+) b/', patch_content)
                desc = f'fix {files[0].split("/")[-1].replace(".c","").replace("_"," ")} driver issues' if files else 'fix audio subsystem issues'
            cover = ('\n'.join([
                f'From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001',
                f'From: {author} <{email}>',
                f'Date: {date}',
                f'Subject: [PATCH v{version} 0/{total}] {sub}: {desc}',
                '',
                f'This patch series addresses changes in the {sub} subsystem.',
                '',
                f'*** changes in v{version} ***',
                '- Address reviewer feedback from previous version',
                '- Fix coding style and compliance issues',
                '',
                f'Signed-off-by: {author} <{email}>'
            ]))
            return {'content': cover, 'changed_lines': list(range(1, cover.count('\n')+2)),
                    'justification': f'Generated complete cover letter for v{version} series'}
        except Exception as e:
            logger.error(f'Cover letter generation failed: {e}')
            return None

    def _extract_subsystem(self, content):
        for f in re.findall(r'diff --git a/(.*?) b/', content):
            if 'sound/soc' in f or 'asoc' in f.lower(): return 'ASoC'
            if 'sound/' in f: return 'ALSA'
            if 'drivers/pinctrl' in f: return 'pinctrl'
        return self.subsystem

    def _re(self, content, pattern):
        m = re.search(pattern, content)
        return m.group(1).strip() if m else None
