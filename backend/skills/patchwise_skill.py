from __future__ import annotations

import re

from core.patchwise_skill import PatchWiseSkill as CorePatchWiseSkill


class PatchWiseSkill(CorePatchWiseSkill):
    async def _ensure_source_files(self, patch_content, kernel_version):
        try:
            import aiohttp
        except Exception:
            aiohttp = None
            import httpx
        from pathlib import Path

        file_paths = re.findall(r'diff --git a/(\S+) b/', patch_content)
        missing, fetched = [], []
        for fp in file_paths:
            local = Path(f'/workspace/kernel_source/{fp}')
            if local.exists():
                continue
            try:
                url = (
                    f'https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git'
                    f'/plain/{fp}?h=v{kernel_version}'
                )
                if aiohttp is not None:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                            if resp.status == 200:
                                local.parent.mkdir(parents=True, exist_ok=True)
                                local.write_text(await resp.text())
                                fetched.append(fp)
                            else:
                                missing.append(fp)
                else:
                    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            local.parent.mkdir(parents=True, exist_ok=True)
                            local.write_text(resp.text)
                            fetched.append(fp)
                        else:
                            missing.append(fp)
            except Exception:
                missing.append(fp)
        return {'fetched': fetched, 'missing': missing, 'all_available': len(missing) == 0}

    async def run_with_fallback(self, patch_content, kernel_version):
        status = await self._ensure_source_files(patch_content, kernel_version)
        if not status['all_available'] and status['missing']:
            missing_list = chr(10).join([f'- {f}' for f in status['missing'][:5]])
            return {
                'status': 'NEEDS_SOURCE',
                'message': (
                    f'Kernel source files needed for full analysis:{chr(10)}{missing_list}{chr(10)}{chr(10)}'
                    f'Please provide your local kernel source path in the Context section,{chr(10)}'
                    f'or proceeding with QGenie AI review (reduced accuracy).'
                ),
                'fallback': True,
                'missing_files': status['missing'],
            }
        return await self._run_full_patchwise(patch_content)

    async def _run_full_patchwise(self, patch_content):
        return self.review_patch_file(patch_content=patch_content)
