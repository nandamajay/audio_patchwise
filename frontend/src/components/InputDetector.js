import { useEffect } from 'react';

export const INPUT_PATTERNS = {
  LORE_URL: /https?:\/\/(lore|lkml)\.kernel\.org\/[^\s]+/i,
  LORE_ALSA: /https?:\/\/(lore|lkml)\.kernel\.org\/alsa-devel\/[^\s]+/i,
  GERRIT_URL: /https?:\/\/[^\s]+gerrit[^\s]+\/c\/[^\s]+/,
  GITHUB_PR: /https?:\/\/github\.com\/[^\s]+\/pull\/[0-9]+/,
  PATCH_FILE: /^From [0-9a-f]{40} Mon Sep 17/m,
  DIFF_CONTENT: /^(---|\+\+\+|@@)/m,
  GIT_FORMAT_PATCH: /^Subject: \[PATCH/m,
};

export function detectInputType(value) {
  if (!value || value.trim() === '') return 'EMPTY';
  const trimmed = value.trim();

  if (INPUT_PATTERNS.LORE_URL.test(trimmed)) return 'LORE_URL';
  if (INPUT_PATTERNS.GERRIT_URL.test(trimmed)) return 'GERRIT_URL';
  if (INPUT_PATTERNS.GITHUB_PR.test(trimmed)) return 'GITHUB_PR';

  if (INPUT_PATTERNS.PATCH_FILE.test(trimmed)) return 'RAW_PATCH';
  if (INPUT_PATTERNS.GIT_FORMAT_PATCH.test(trimmed)) return 'RAW_PATCH';
  if (INPUT_PATTERNS.DIFF_CONTENT.test(trimmed)) return 'RAW_DIFF';

  return 'UNKNOWN';
}

export function useInputAutoDetect(value, currentTab, onTabSwitch, onBanner) {
  useEffect(() => {
    if (!value) return;
    const detected = detectInputType(value);

    if (detected === 'LORE_URL' && currentTab !== 'LORE') {
      onTabSwitch('LORE');
      onBanner({
        type: 'info',
        message: 'Lore.kernel.org URL detected - switched to LORE tab. Fetching patch...',
        autoClose: 4000,
      });
    } else if (detected === 'GERRIT_URL' && currentTab !== 'GERRIT') {
      onTabSwitch('GERRIT');
      onBanner({
        type: 'info',
        message: 'Gerrit URL detected - switched to GERRIT tab.',
        autoClose: 4000,
      });
    }
  }, [value, currentTab, onTabSwitch, onBanner]);
}
