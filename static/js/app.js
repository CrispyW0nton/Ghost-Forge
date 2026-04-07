/* ============================================================
   UV & Texture Generator — Frontend App
   ============================================================ */

'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let meshFile        = null;
let refImageFile    = null;
let currentJobId    = null;
let pollInterval    = null;
let threeScene      = null;

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const meshDropZone    = document.getElementById('mesh-drop-zone');
const meshInput       = document.getElementById('mesh-input');
const meshPreview     = document.getElementById('mesh-preview');
const meshFilename    = document.getElementById('mesh-filename');
const meshClear       = document.getElementById('mesh-clear');

const refDropZone     = document.getElementById('ref-drop-zone');
const refInput        = document.getElementById('ref-input');
const refPreview      = document.getElementById('ref-preview');
const refFilename     = document.getElementById('ref-filename');
const refClear        = document.getElementById('ref-clear');
const refThumb        = document.getElementById('ref-thumb');

const promptInput     = document.getElementById('prompt-input');
const textureSizeEl   = document.getElementById('texture-size');
const outputFormatEl  = document.getElementById('output-format');
const useAiEl         = document.getElementById('use-ai');
const aiStepsEl       = document.getElementById('ai-steps');
const aiStepsVal      = document.getElementById('ai-steps-val');
const aiStepsSetting  = document.getElementById('ai-steps-setting');

const generateBtn     = document.getElementById('generate-btn');
const progressCard    = document.getElementById('progress-card');
const progressStage   = document.getElementById('progress-stage');
const progressBar     = document.getElementById('progress-bar');
const progressPct     = document.getElementById('progress-pct');

const emptyState      = document.getElementById('empty-state');
const resultsSection  = document.getElementById('results-section');
const texturePreview  = document.getElementById('texture-preview');
const uvPreview       = document.getElementById('uv-preview');
const statsGrid       = document.getElementById('stats-grid');
const threeContainer  = document.getElementById('three-container');

const dlMesh          = document.getElementById('dl-mesh');
const dlTexture       = document.getElementById('dl-texture');
const dlUv            = document.getElementById('dl-uv');

// ---------------------------------------------------------------------------
// File drop helpers
// ---------------------------------------------------------------------------

function setupDropZone(dropZone, inputEl, onFile) {
  dropZone.addEventListener('click', () => inputEl.click());

  dropZone.addEventListener('dragover', e => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) onFile(file);
  });

  inputEl.addEventListener('change', () => {
    const file = inputEl.files[0];
    if (file) onFile(file);
  });
}

function setMeshFile(file) {
  meshFile = file;
  meshFilename.textContent = file.name;
  meshDropZone.style.display = 'none';
  meshPreview.style.display  = 'flex';
}

function clearMeshFile() {
  meshFile = null;
  meshInput.value = '';
  meshDropZone.style.display = '';
  meshPreview.style.display  = 'none';
}

function setRefFile(file) {
  refImageFile = file;
  refFilename.textContent = file.name;
  const url = URL.createObjectURL(file);
  refThumb.src = url;
  refDropZone.style.display = 'none';
  refPreview.style.display  = 'flex';
}

function clearRefFile() {
  refImageFile = null;
  refInput.value = '';
  refDropZone.style.display = '';
  refPreview.style.display  = 'none';
}

setupDropZone(meshDropZone, meshInput, setMeshFile);
setupDropZone(refDropZone, refInput, setRefFile);
meshClear.addEventListener('click', clearMeshFile);
refClear.addEventListener('click', clearRefFile);

// ---------------------------------------------------------------------------
// Quick prompts
// ---------------------------------------------------------------------------

document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => {
    promptInput.value = chip.dataset.prompt;
    promptInput.focus();
  });
});

// ---------------------------------------------------------------------------
// AI toggle
// ---------------------------------------------------------------------------

useAiEl.addEventListener('change', () => {
  aiStepsSetting.style.display = useAiEl.checked ? '' : 'none';
});

aiStepsEl.addEventListener('input', () => {
  aiStepsVal.textContent = aiStepsEl.value;
});

// ---------------------------------------------------------------------------
// Generate
// ---------------------------------------------------------------------------

generateBtn.addEventListener('click', async () => {
  if (!meshFile) {
    alert('Please upload a 3D model first.');
    return;
  }
  if (!promptInput.value.trim()) {
    alert('Please enter a texture description.');
    return;
  }

  startProcessing();

  const formData = new FormData();
  formData.append('mesh', meshFile);
  formData.append('prompt', promptInput.value.trim());
  formData.append('texture_size', textureSizeEl.value);
  formData.append('output_format', outputFormatEl.value);
  formData.append('use_ai', useAiEl.checked ? 'true' : 'false');
  formData.append('ai_steps', aiStepsEl.value);
  if (refImageFile) formData.append('reference', refImageFile);

  try {
    const res = await fetch('/api/jobs', { method: 'POST', body: formData });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    const data = await res.json();
    currentJobId = data.job_id;
    startPolling(currentJobId);
  } catch (e) {
    stopProcessing();
    alert(`Failed to start job: ${e.message}`);
  }
});

// ---------------------------------------------------------------------------
// Progress polling
// ---------------------------------------------------------------------------

function startPolling(jobId) {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) return;
      const job = await res.json();
      updateProgress(job);

      if (job.status === 'done') {
        clearInterval(pollInterval);
        onJobComplete(job);
      } else if (job.status === 'error') {
        clearInterval(pollInterval);
        onJobError(job.error);
      }
    } catch (_) {}
  }, 1000);
}

function updateProgress(job) {
  progressStage.textContent = job.stage || 'Processing…';
  progressBar.style.width   = (job.progress || 0) + '%';
  progressPct.textContent   = (job.progress || 0) + '%';
}

// ---------------------------------------------------------------------------
// UI state transitions
// ---------------------------------------------------------------------------

function startProcessing() {
  generateBtn.disabled = true;
  generateBtn.innerHTML = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation:spin 1s linear infinite">
      <circle cx="12" cy="12" r="10" stroke-dasharray="40" stroke-dashoffset="10"/>
    </svg>
    Processing…`;

  // Inject spin keyframe if not already
  if (!document.querySelector('#spin-style')) {
    const s = document.createElement('style');
    s.id = 'spin-style';
    s.textContent = '@keyframes spin { to { transform: rotate(360deg); } }';
    document.head.appendChild(s);
  }

  progressCard.style.display   = '';
  emptyState.style.display     = 'none';
  resultsSection.style.display = 'none';
  updateProgress({ stage: 'Queued', progress: 0 });
}

function stopProcessing() {
  generateBtn.disabled = false;
  generateBtn.innerHTML = `
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polygon points="5,3 19,12 5,21"/>
    </svg>
    Generate UV &amp; Texture`;
}

function onJobComplete(job) {
  stopProcessing();
  progressCard.style.display   = 'none';
  resultsSection.style.display = '';

  const result  = job.result || {};
  const jobId   = job.id;

  // Texture image
  texturePreview.src = `/api/jobs/${jobId}/preview/texture?t=${Date.now()}`;
  uvPreview.src      = `/api/jobs/${jobId}/preview/uv_layout?t=${Date.now()}`;

  // Stats
  const os = result.original_stats || {};
  const us = result.uv_stats || {};
  renderStats([
    { label: 'Original Vertices', value: (os.vertices || 0).toLocaleString() },
    { label: 'Original Faces',    value: (os.faces || 0).toLocaleString() },
    { label: 'UV Vertices',       value: (us.unwrapped_vertices || 0).toLocaleString(), sub: 'after seam splitting' },
    { label: 'UV Expansion',      value: `${((us.uv_expansion || 1) * 100).toFixed(0)}%`, sub: 'vertex overhead' },
    { label: 'Texture Size',      value: `${result.texture_size || '—'}px` },
    { label: 'Process Time',      value: `${result.processing_time_seconds || 0}s` },
  ]);

  // Download buttons
  dlMesh.onclick    = () => downloadFile(jobId, 'mesh');
  dlTexture.onclick = () => downloadFile(jobId, 'texture');
  dlUv.onclick      = () => downloadFile(jobId, 'uv_layout');

  // 3D Preview (GLB)
  if (result.output_mesh && result.output_mesh.endsWith('.glb')) {
    loadThreePreview(`/api/jobs/${jobId}/download/mesh`);
  }
}

function onJobError(error) {
  stopProcessing();
  progressCard.style.display = 'none';
  emptyState.style.display   = '';
  alert(`Processing failed: ${error}`);
}

// ---------------------------------------------------------------------------
// Stats renderer
// ---------------------------------------------------------------------------

function renderStats(stats) {
  statsGrid.innerHTML = stats.map(s => `
    <div class="stat-item">
      <div class="stat-item__label">${s.label}</div>
      <div class="stat-item__value">${s.value}</div>
      ${s.sub ? `<div class="stat-item__sub">${s.sub}</div>` : ''}
    </div>
  `).join('');
}

// ---------------------------------------------------------------------------
// Download helper
// ---------------------------------------------------------------------------

function downloadFile(jobId, type) {
  const a = document.createElement('a');
  a.href = `/api/jobs/${jobId}/download/${type}`;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ---------------------------------------------------------------------------
// Three.js 3D Preview
// ---------------------------------------------------------------------------

function loadThreePreview(glbUrl) {
  // Clear previous scene
  if (threeScene) {
    threeScene.renderer.dispose();
    threeContainer.innerHTML = '';
  }

  const width  = threeContainer.clientWidth;
  const height = threeContainer.clientHeight || 400;

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(width, height);
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.outputEncoding = THREE.sRGBEncoding;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.2;
  threeContainer.appendChild(renderer.domElement);

  const scene  = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, width / height, 0.01, 1000);

  // Lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
  scene.add(ambientLight);
  const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight1.position.set(5, 10, 5);
  scene.add(dirLight1);
  const dirLight2 = new THREE.DirectionalLight(0x8080ff, 0.3);
  dirLight2.position.set(-5, -5, -5);
  scene.add(dirLight2);

  // Controls
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.autoRotate    = true;
  controls.autoRotateSpeed = 0.8;

  // Load GLB
  const loader = new THREE.GLTFLoader();
  loader.load(
    glbUrl,
    (gltf) => {
      const model = gltf.scene;
      // Center and scale
      const box    = new THREE.Box3().setFromObject(model);
      const center = box.getCenter(new THREE.Vector3());
      const size   = box.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z);
      const scale  = 2.5 / maxDim;
      model.scale.setScalar(scale);
      model.position.sub(center.multiplyScalar(scale));
      scene.add(model);
      camera.position.set(0, 0, 4);
      controls.update();
    },
    undefined,
    (err) => {
      console.warn('GLB preview failed:', err);
      threeContainer.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#5a5a7a;font-size:13px;">3D preview unavailable</div>';
    }
  );

  // Animate
  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  // Resize
  const observer = new ResizeObserver(() => {
    const w = threeContainer.clientWidth;
    const h = threeContainer.clientHeight || 400;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  });
  observer.observe(threeContainer);

  threeScene = { renderer, scene, camera, controls };
}
