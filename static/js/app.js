(() => {
  const form        = document.getElementById('lutForm');
  const generateBtn = document.getElementById('generateBtn');
  const btnText     = generateBtn.querySelector('.btn-text');
  const spinner     = generateBtn.querySelector('.spinner');
  const resultPanel = document.getElementById('resultPanel');
  const errorPanel  = document.getElementById('errorPanel');
  const errorMsg    = document.getElementById('errorMsg');
  const progressWrap = document.getElementById('progressWrap');
  const progressBar  = document.getElementById('progressBar');
  const progressLabel = document.getElementById('progressLabel');

  let extractedFrames = [];   // base64 data URLs
  let videoFile = null;

  // --- Drag & drop ---
  function setupDropZone(zoneId, inputId, infoId, onFile) {
    const zone  = document.getElementById(zoneId);
    const input = document.getElementById(inputId);
    const info  = document.getElementById(infoId);

    zone.addEventListener('click', (e) => {
      if (!e.target.closest('button')) input.click();
    });
    input.addEventListener('change', () => { if (input.files[0]) handleFile(input.files[0]); });
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) {
        const dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
        handleFile(file);
      }
    });

    function handleFile(file) {
      zone.classList.add('has-file');
      info.textContent = `✓ ${file.name} (${formatSize(file.size)})`;
      info.hidden = false;
      if (onFile) onFile(file);
    }
  }

  setupDropZone('videoDropZone', 'videoInput', 'videoInfo', async (file) => {
    videoFile = file;
    extractedFrames = [];
    setProgress(0, 'Extraction des frames…');
    progressWrap.hidden = false;
    try {
      extractedFrames = await extractFrames(file, 20, (pct) => {
        setProgress(pct, `Extraction des frames… ${pct}%`);
      });
      setProgress(100, `✓ ${extractedFrames.length} frames extraites`);
    } catch (e) {
      progressWrap.hidden = true;
      showError('Impossible d\'extraire les frames : ' + e.message);
    }
  });

  setupDropZone('refDropZone', 'refInput', 'refInfo', (file) => {
    const preview     = document.getElementById('refPreview');
    const previewWrap = document.getElementById('refPreviewWrap');
    const reader = new FileReader();
    reader.onload = (e) => { preview.src = e.target.result; previewWrap.hidden = false; };
    reader.readAsDataURL(file);
  });

  // --- Client-side frame extraction ---
  function extractFrames(file, nFrames, onProgress) {
    return new Promise((resolve, reject) => {
      const video  = document.createElement('video');
      const canvas = document.createElement('canvas');
      const ctx    = canvas.getContext('2d');
      const url    = URL.createObjectURL(file);
      video.src    = url;
      video.muted  = true;
      video.preload = 'metadata';

      video.addEventListener('error', () => {
        URL.revokeObjectURL(url);
        reject(new Error('Format vidéo non supporté par le navigateur.'));
      });

      video.addEventListener('loadedmetadata', async () => {
        const duration = video.duration;
        if (!isFinite(duration) || duration === 0) {
          URL.revokeObjectURL(url);
          reject(new Error('Durée vidéo non lisible (format non supporté).'));
          return;
        }

        // 320px wide is sufficient for color statistics — keeps payload small
        const W = 320;
        const H = Math.round(W * video.videoHeight / video.videoWidth);
        canvas.width  = W;
        canvas.height = H;

        const frames = [];
        for (let i = 0; i < nFrames; i++) {
          const t = i === 0 ? 0.01 : (duration * i) / (nFrames - 1);
          try {
            await seekTo(video, t);
            ctx.drawImage(video, 0, 0, W, H);
            frames.push(canvas.toDataURL('image/jpeg', 0.75));
          } catch (e) {
            // skip bad frame
          }
          if (onProgress) onProgress(Math.round(((i + 1) / nFrames) * 100));
        }

        URL.revokeObjectURL(url);
        if (frames.length === 0) reject(new Error('Aucune frame extraite.'));
        else resolve(frames);
      });

      video.load();
    });
  }

  function seekTo(video, time) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('seek timeout')), 5000);
      video.addEventListener('seeked', () => { clearTimeout(timeout); resolve(); }, { once: true });
      video.currentTime = time;
    });
  }

  // --- Presets ---
  document.querySelectorAll('.preset').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.getElementById('descriptionInput').value = btn.dataset.text;
    });
  });

  // --- Form submit ---
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    resultPanel.hidden = true;
    errorPanel.hidden  = true;

    if (!videoFile || extractedFrames.length === 0) {
      showError('Sélectionne une vidéo et attends l\'extraction des frames.');
      return;
    }

    setLoading(true);

    const fd = new FormData();
    extractedFrames.forEach(f => fd.append('frames[]', f));

    const refInput = document.getElementById('refInput');
    if (refInput.files[0]) fd.append('reference', refInput.files[0]);

    fd.append('description', document.getElementById('descriptionInput').value);
    fd.append('lut_name',    document.getElementById('lutNameInput').value || 'My LUT');

    try {
      const res  = await fetch('/generate', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) { showError(data.error || 'Erreur inconnue'); return; }
      showResult(data);
    } catch (err) {
      showError('Erreur réseau : ' + err.message);
    } finally {
      setLoading(false);
    }
  });

  // --- Reset ---
  document.getElementById('resetBtn').addEventListener('click', () => {
    resultPanel.hidden = true;
    errorPanel.hidden  = true;
    progressWrap.hidden = true;
    form.reset();
    videoFile = null;
    extractedFrames = [];
    ['videoInfo','refInfo'].forEach(id => document.getElementById(id).hidden = true);
    document.getElementById('refPreviewWrap').hidden = true;
    ['videoDropZone','refDropZone'].forEach(id => document.getElementById(id).classList.remove('has-file'));
  });

  // --- Helpers ---
  function setLoading(on) {
    generateBtn.disabled = on;
    btnText.textContent  = on ? 'Génération en cours…' : 'Générer le LUT';
    spinner.hidden       = !on;
  }

  function setProgress(pct, label) {
    progressBar.style.width = pct + '%';
    progressLabel.textContent = label;
  }

  function showError(msg) {
    errorMsg.textContent = msg;
    errorPanel.hidden    = false;
  }

  function formatSize(bytes) {
    if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' Go';
    if (bytes >= 1e6) return (bytes / 1e6).toFixed(0) + ' Mo';
    return (bytes / 1e3).toFixed(0) + ' Ko';
  }

  function showResult(data) {
    document.getElementById('resultTitle').textContent = `"${data.lut_name}" — prêt !`;
    const dlBtn = document.getElementById('downloadBtn');
    dlBtn.href  = data.download_url;
    dlBtn.download = data.filename;
    dlBtn.textContent = `⬇ Télécharger ${data.filename}`;

    const r = data.style_params;
    document.getElementById('reasoning').textContent = r.reasoning || '';

    const paramLabels = {
      temperature_shift:             'Température',
      tint_shift:                    'Teinte (tint)',
      exposure:                      'Exposition (stops)',
      contrast:                      'Contraste',
      highlights:                    'Hautes lumières',
      shadows:                       'Ombres',
      saturation:                    'Saturation',
      vibrance:                      'Vibrance',
      shadow_lift:                   'Lift des ombres (matte)',
      highlight_roll:                'Roll-off hautes lumières',
      split_tone_shadow_strength:    'Split tone — force ombres',
      split_tone_highlight_strength: 'Split tone — force HL',
    };
    const table = document.getElementById('paramsTable');
    table.innerHTML = '';
    for (const [key, label] of Object.entries(paramLabels)) {
      if (!(key in r) || typeof r[key] !== 'number') continue;
      const val  = r[key];
      const barW = Math.round(Math.abs(val) * 60);
      const barClass = val === 0 ? 'zero' : val > 0 ? 'bar' : 'bar neg';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${label}</td>
        <td><div class="bar-wrap">
          <span class="${barClass}" style="width:${Math.max(barW,2)}px"></span>
          ${val > 0 ? '+' : ''}${val.toFixed(2)}
        </div></td>`;
      table.appendChild(tr);
    }

    const src = data.source_analysis;
    const h   = src.histogram;
    document.getElementById('analysisInfo').innerHTML = `
      <strong>${src.frames_analyzed} frames</strong> analysées &nbsp;·&nbsp;
      Lab moyen : <strong>L=${src.lab_mean[0].toFixed(1)}, a=${src.lab_mean[1].toFixed(1)}, b=${src.lab_mean[2].toFixed(1)}</strong><br>
      Canaux RGB — Rouge : moy <strong>${h.r.mean.toFixed(0)}</strong> · Vert : moy <strong>${h.g.mean.toFixed(0)}</strong> · Bleu : moy <strong>${h.b.mean.toFixed(0)}</strong><br>
      Image de référence : <strong>${data.has_reference ? 'utilisée ✓' : 'non fournie'}</strong>
    `;

    resultPanel.hidden = false;
    resultPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
})();
