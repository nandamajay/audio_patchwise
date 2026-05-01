import React, { useState, useEffect, useRef, useCallback } from 'react';

import { detectInputType, useInputAutoDetect } from './InputDetector';

const TABS = ['RAW', 'FILE', 'GERRIT', 'LORE'];

function readFilesAsPatchText(fileList) {
  const readers = fileList.map((file) => new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(`# FILE: ${file.name}\n${String(reader.result || '')}`);
    };
    reader.onerror = () => resolve(`# FILE: ${file.name}\n`);
    reader.readAsText(file);
  }));

  return Promise.all(readers).then((chunks) => chunks.join('\n\n').trim());
}

function buildCombinedLorePatch(patches) {
  if (!Array.isArray(patches) || patches.length === 0) return '';
  return patches.map((p, i) => {
    const filename = `000${p.index ?? i}-lore.patch`;
    return `# FILE: ${filename}\n${p.content || ''}`;
  }).join('\n\n');
}

export default function PatchInput({ onPatchReady = () => {}, value = '', onChange = () => {} }) {
  const [activeTab, setActiveTab] = useState('RAW');
  const [rawValue, setRawValue] = useState(value || '');
  const [loreUrl, setLoreUrl] = useState('');
  const [gerritUrl, setGerritUrl] = useState('');
  const [files, setFiles] = useState([]);
  const [fetchStatus, setFetchStatus] = useState(null);
  const [banner, setBanner] = useState(null);
  const [fetchedPatches, setFetchedPatches] = useState([]);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (typeof value === 'string' && value !== rawValue && activeTab === 'RAW') {
      setRawValue(value);
    }
  }, [value, rawValue, activeTab]);

  const showBanner = useCallback((nextBanner) => {
    setBanner((prev) => {
      if (prev && prev.message === nextBanner.message) return prev;
      return nextBanner;
    });
  }, []);

  useInputAutoDetect(rawValue, activeTab, setActiveTab, showBanner);

  useEffect(() => {
    if (!rawValue.trim()) return;
    const detected = detectInputType(rawValue.trim());

    if (detected === 'LORE_URL') {
      const url = rawValue.trim();
      setActiveTab('LORE');
      setLoreUrl(url);
      setRawValue('');
      onChange('');
      setBanner({
        type: 'info',
        icon: 'LINK',
        message: 'Lore.kernel.org URL detected. Switched to LORE tab and fetching patches...',
        autoClose: 5000,
      });
      fetchLorePatches(url);
    } else if (detected === 'GERRIT_URL') {
      const url = rawValue.trim();
      setActiveTab('GERRIT');
      setGerritUrl(url);
      setRawValue('');
      onChange(url);
      setBanner({
        type: 'info',
        icon: 'GERRIT',
        message: 'Gerrit URL detected. Switched to GERRIT tab.',
        autoClose: 4000,
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawValue]);

  useEffect(() => {
    if (banner?.autoClose) {
      const t = setTimeout(() => setBanner(null), banner.autoClose);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [banner]);

  const fetchLorePatches = async (url) => {
    if (!url.trim()) return;
    setFetchStatus({ state: 'fetching', message: 'Fetching patches from lore.kernel.org...' });
    setFetchedPatches([]);

    try {
      const resp = await fetch('/api/fetch-lore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      });

      let payload = null;
      try {
        payload = await resp.json();
      } catch {
        payload = null;
      }

      if (!resp.ok) {
        throw new Error(payload?.detail || 'Fetch failed');
      }

      const data = payload || {};
      const patches = Array.isArray(data.patches) ? data.patches : [];
      setFetchedPatches(patches);
      const combinedPatch = buildCombinedLorePatch(patches);
      onChange(combinedPatch);

      setFetchStatus({
        state: 'success',
        message: `Fetched ${patches.length} patch(es) - Series: ${data.series_title || 'Unknown Series'}`,
        version: data.version,
        thread_count: data.thread_count,
        prev_version_url: data.prev_version_url,
      });

      onPatchReady({
        type: 'lore',
        patches,
        url: url.trim(),
        series_title: data.series_title,
        version: data.version,
        thread: data.thread,
        prev_version_url: data.prev_version_url,
      });
    } catch (err) {
      setFetchStatus({
        state: 'error',
        message: `Fetch failed: ${err.message}. Proceeding with standalone review.`,
      });
    }
  };

  const handleFileChange = async (e) => {
    const newFiles = Array.from(e.target.files || []);
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name));
      const added = newFiles.filter((f) => !existing.has(f.name));
      return [...prev, ...added];
    });

    const merged = await readFilesAsPatchText(newFiles);
    if (merged) {
      onChange(merged);
      onPatchReady({ type: 'file', content: merged, files: newFiles.map((f) => f.name) });
    }
  };

  const removeFile = async (name) => {
    const updated = files.filter((f) => f.name !== name);
    setFiles(updated);
    if (!updated.length) {
      onChange('');
      return;
    }
    const merged = await readFilesAsPatchText(updated);
    onChange(merged);
  };

  return (
    <div className="patch-input-container glass card">
      {banner && (
        <div className={`auto-detect-banner banner-${banner.type || 'info'}`}>
          <span>{banner.message}</span>
          <button type="button" onClick={() => setBanner(null)}>x</button>
        </div>
      )}

      <div className="tab-row" style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            className={`btn ${activeTab === tab ? '' : 'secondary'} tab-btn`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === 'RAW' && (
        <div className="tab-panel">
          <p className="small tab-hint">
            Paste patch text directly.
            <span className="hint-tip"> URLs are auto-detected.</span>
          </p>
          <textarea
            className="textarea patch-textarea"
            value={rawValue}
            onChange={(e) => {
              const next = e.target.value;
              setRawValue(next);
              onChange(next);
            }}
            placeholder="Paste raw patch content or any URL (lore.kernel.org, Gerrit)..."
            rows={12}
          />
        </div>
      )}

      {activeTab === 'FILE' && (
        <div className="tab-panel">
          <p className="small tab-hint">Upload one or more .patch files</p>
          <div
            className="dropzone"
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={async (e) => {
              e.preventDefault();
              const dropped = Array.from(e.dataTransfer.files || []).filter(
                (f) => f.name.endsWith('.patch') || f.name.endsWith('.diff'),
              );
              const mergedFiles = [...files, ...dropped.filter((f) => !files.some((p) => p.name === f.name))];
              setFiles(mergedFiles);
              const merged = await readFilesAsPatchText(mergedFiles);
              onChange(merged);
              onPatchReady({ type: 'file', content: merged, files: mergedFiles.map((f) => f.name) });
            }}
            style={{ border: '1px dashed var(--glass-border)', borderRadius: 8, padding: 14, cursor: 'pointer' }}
          >
            <div className="dropzone-inner" style={{ display: 'grid', gap: 4 }}>
              <span className="dropzone-icon">FILE</span>
              <span>Drop .patch files here or click to browse</span>
              <span className="small dropzone-hint">Multiple files supported</span>
            </div>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".patch,.diff"
            multiple
            style={{ display: 'none' }}
            onChange={handleFileChange}
          />

          {files.length > 0 && (
            <div className="file-chips" style={{ marginTop: 10, display: 'grid', gap: 6 }}>
              {files.map((f) => (
                <div key={f.name} className="file-chip" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="chip-name">{f.name}</span>
                  <span className="small chip-size">{(f.size / 1024).toFixed(1)}KB</span>
                  <button
                    type="button"
                    className="btn secondary chip-remove"
                    onClick={() => removeFile(f.name)}
                  >x</button>
                </div>
              ))}
              <div className="small file-count">
                {files.length} file{files.length > 1 ? 's' : ''} selected
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'GERRIT' && (
        <div className="tab-panel">
          <p className="small tab-hint">Paste Gerrit review URL</p>
          <input
            className="input url-input"
            type="url"
            value={gerritUrl}
            onChange={(e) => {
              const next = e.target.value;
              setGerritUrl(next);
              onChange(next);
            }}
            placeholder="https://gerrit.example.com/c/project/+/123456"
          />
        </div>
      )}

      {activeTab === 'LORE' && (
        <div className="tab-panel">
          <p className="small tab-hint">Paste lore.kernel.org patch URL</p>
          <div className="lore-input-row" style={{ display: 'flex', gap: 8 }}>
            <input
              className="input url-input"
              type="url"
              value={loreUrl}
              onChange={(e) => setLoreUrl(e.target.value)}
              placeholder="https://lore.kernel.org/alsa-devel/..."
            />
            <button
              type="button"
              className="btn fetch-btn"
              onClick={() => fetchLorePatches(loreUrl)}
              disabled={!loreUrl.trim() || fetchStatus?.state === 'fetching'}
            >
              {fetchStatus?.state === 'fetching' ? 'Fetching...' : 'Fetch'}
            </button>
          </div>

          {fetchStatus && (
            <div className={`fetch-status status-${fetchStatus.state}`} style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <span>{fetchStatus.message}</span>
              {fetchStatus.version ? <span className="badge fetch-badge">v{fetchStatus.version}</span> : null}
              {fetchStatus.thread_count ? (
                <span className="badge fetch-badge">{fetchStatus.thread_count} thread replies</span>
              ) : null}
              {fetchStatus.prev_version_url ? (
                <span className="badge fetch-badge prev-version">Previous version found</span>
              ) : null}
            </div>
          )}

          {fetchedPatches.length > 0 && (
            <div className="fetched-patches" style={{ marginTop: 10, display: 'grid', gap: 6 }}>
              <div className="fetched-header small">
                {fetchedPatches.length} patch(es) fetched and ready for review:
              </div>
              {fetchedPatches.map((p, i) => (
                <div key={`${p.message_id || i}`} className="fetched-patch-item" style={{ display: 'flex', gap: 8 }}>
                  <span className="patch-num">[{p.index}/{Math.max(1, fetchedPatches.length - 1)}]</span>
                  <span className="patch-subject">{p.subject}</span>
                  <span className="small patch-size">{p.size}B</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
