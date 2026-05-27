(() => {
  const form        = document.getElementById('lutForm');
  const generateBtn = document.getElementById('generateBtn');
  const btnText     = generateBtn.querySelector('.btn-text');
  const spinner     = generateBtn.querySelector('.spinner');
  const resultPanel = document.getElementById('resultPanel');
  const errorPanel  = document.getElementById('errorPanel');
  const errorMsg    = document.getElementById('errorMsg');

  // --- Drag & drop ---
  function setupDropZone(zoneId, inputId, infoId, onFile) {
    const zone  = document.getElementById(zoneId);
    const input = document.getElementById(inputId);
    const info  = document.getElementById(infoId);

    zone.addEventListener('click', (e) => {
      if (!e.target.closest('button')) input.click();
    });

    input.addEventListener('change', () => {
      if (input.files[0]) handleFile(input.files[0]);
    });

    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) {
        // Transfer to input
        const dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
        handleFile(file);
      }
    });

    function handleFile(file) {
      zone.classList.add('has-file');
      info.textContent = `✓ ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} Mo)`;
      info.hidden = false;
      if (onFile) onFile(file);
    }
  }

  setupDropZone('videoDropZone', 'videoInput', 'videoInfo');

  setupDropZone('refDropZone', 'refInput', 'refInfo', (file) => {
    const preview     = document.getElementById('refPreview');
    const previewWrap = document.getElementById('refPreviewWrap');
    const reader = new FileReader();
    reader.onload = (e) => {
      preview.src = e.target.result;
      previewWrap.hidden = false;
    };
    reader.readAsDataURL(file);
  });

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

    const videoInput = document.getElementById('videoInput');
    if (!videoInput.files[0]) {
      showError('Veuillez sélectionner une vidéo.');
      return;
    }

    setLoading(true);

    const fd = new FormData(form);

    try {
      const res  = await fetch('/generate', { method: 'POST', body: fd });
      const data = await res.json();

      if (!res.ok) {
        showError(data.error || 'Erreur inconnue');
        return;
      }

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
    form.reset();
    document.getElementById('videoInfo').hidden = true;
    document.getElementById('refInfo').hidden   = true;
    document.getElementById('refPreviewWrap').hidden = true;
    document.getElementById('videoDropZone').classList.remove('has-file');
    document.getElementById('refDropZone').classList.remove('has-file');
  });

  // --- Helpers ---
  function setLoading(on) {
    generateBtn.disabled = on;
    btnText.textContent  = on ? 'Génération en cours…' : 'Générer le LUT';
    spinner.hidden       = !on;
  }

  function showError(msg) {
    errorMsg.textContent = msg;
    errorPanel.hidden    = false;
  }

  function showResult(data) {
    document.getElementById('resultTitle').textContent = `"${data.lut_name}" — prêt !`;

    const dlBtn = document.getElementById('downloadBtn');
    dlBtn.href  = data.download_url;
    dlBtn.download = data.filename;
    dlBtn.textContent = `⬇ Télécharger ${data.filename}`;

    // Reasoning
    const r = data.style_params;
    document.getElementById('reasoning').textContent =
      r.reasoning || 'Paramètres appliqués avec succès.';

    // Params table
    const paramLabels = {
      temperature_shift:            'Température',
      tint_shift:                   'Teinte (tint)',
      exposure:                     'Exposition (stops)',
      contrast:                     'Contraste',
      highlights:                   'Hautes lumières',
      shadows:                      'Ombres',
      saturation:                   'Saturation',
      vibrance:                     'Vibrance',
      shadow_lift:                  'Lift des ombres (matte)',
      highlight_roll:               'Roll-off hautes lumières',
      split_tone_shadow_strength:   'Split tone — force ombres',
      split_tone_highlight_strength:'Split tone — force HL',
    };
    const table = document.getElementById('paramsTable');
    table.innerHTML = '';
    for (const [key, label] of Object.entries(paramLabels)) {
      if (!(key in r)) continue;
      const val = r[key];
      if (typeof val !== 'number') continue;
      const tr = document.createElement('tr');
      const barW = Math.round(Math.abs(val) * 60);
      const barClass = val === 0 ? 'zero' : val > 0 ? 'bar' : 'bar neg';
      tr.innerHTML = `
        <td>${label}</td>
        <td>
          <div class="bar-wrap">
            <span class="${barClass}" style="width:${Math.max(barW,2)}px"></span>
            ${val > 0 ? '+' : ''}${val.toFixed(2)}
          </div>
        </td>`;
      table.appendChild(tr);
    }

    // Source analysis
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
