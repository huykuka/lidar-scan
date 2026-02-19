import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

// Setup Scene
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000000);

// Setup Camera
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(15, 15, 15);
camera.lookAt(5, 5, 5);

// Setup Renderer
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
// Clear body to safely append (in case of re-runs or weird states)
// but keep #info
const existingCanvas = document.querySelector('canvas');
if (existingCanvas) existingCanvas.remove();
document.body.appendChild(renderer.domElement);

// Responsiveness: Handle window resize
window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
});

// Setup Controls
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(5, 5, 5);

// Grid Helper
const gridHelper = new THREE.GridHelper(20, 20, 0x444444, 0x222222);
gridHelper.position.set(0, 0, 0); // Optional: lower grid slightly
scene.add(gridHelper);

// Axes Helper
const axesHelper = new THREE.AxesHelper(5);
scene.add(axesHelper);

// Point Cloud Geometry
const geometry = new THREE.BufferGeometry();
const MAX_POINTS = 50000; // Matches backend limit slice or reasonable max
const positions = new Float32Array(MAX_POINTS * 3);
geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

const material = new THREE.PointsMaterial({ size: 0.1, color: 0x00ff00 });
const pointsObj = new THREE.Points(geometry, material);
pointsObj.frustumCulled = false; // Important for dynamic updates
pointsObj.rotation.x = -Math.PI / 2; // Rotate -90 deg to align Z-up data with Y-up scene
pointsObj.rotation.z = -Math.PI / 2; // Rotate -90 deg to align Z-up data with Y-up scene
// pointsObj.rotation.y = -Math.PI / 2; // Rotate -90 deg to align Z-up data with Y-up scene
scene.add(pointsObj);

// WebSocket Connection
const statusEl = document.getElementById('status');
const countEl = document.getElementById('point-count');
const topicSelect = document.getElementById('topic-select');
const versionEl = document.getElementById('version');
const pointSizeEl = document.getElementById('point-size');
const pointColorEl = document.getElementById('point-color');

pointSizeEl.addEventListener('input', (e) => {
    const newSize = parseFloat(e.target.value);
    console.log(`Setting point size to: ${newSize}`);
    material.size = newSize;
});

pointColorEl.addEventListener('input', (e) => {
    console.log(`Setting point color to: ${e.target.value}`);
    material.color.set(e.target.value);
});

let ws;
let currentTopic = '';

async function fetchStatus() {
    try {
        // 1. Fetch Version/Status
        const statusRes = await fetch('/status');
        const statusData = await statusRes.json();
        if (statusData.version) versionEl.textContent = statusData.version;

        // 2. Fetch Dynamic Topics
        const topicsRes = await fetch('/topics');
        const topicsData = await topicsRes.json();
        const topics = topicsData.topics || [];
        
        topicSelect.innerHTML = '';
        topics.forEach(topic => {
            const option = document.createElement('option');
            option.value = topic;
            option.textContent = topic;
            topicSelect.appendChild(option);
        });

        if (topics.length > 0) {
            // Keep current selection if it still exists, otherwise pick first
            if (!topics.includes(currentTopic)) {
                currentTopic = topics[0];
                topicSelect.value = currentTopic;
                connect(currentTopic);
            } else {
                topicSelect.value = currentTopic;
            }
        } else {
             statusEl.textContent = 'No active topics';
        }
    } catch (e) {
        console.error('Error fetching status:', e);
        statusEl.textContent = 'Error loading API';
        versionEl.textContent = 'Unknown';
    }
}

topicSelect.addEventListener('change', (e) => {
    currentTopic = e.target.value;
    connect(currentTopic);
});

function connect(topic) {
    if (ws) {
        // Prevent reconnection logic from firing for the old socket when we manually switch
        ws.onclose = null;
        ws.close();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${topic}`;
    
    console.log(`Connecting to ${wsUrl}`);
    ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        statusEl.textContent = 'Connected';
        statusEl.style.color = '#0f0';
    };

    ws.onmessage = async (event) => {
        try {
            let data = event.data;
            if (data instanceof Blob) {
                data = await data.arrayBuffer();
            }

            if (data instanceof ArrayBuffer) {
                const payload = parseBinaryPointCloud(data);
                if (payload) {
                    updatePointCloud(payload);
                }
            } else {
                const message = JSON.parse(event.data);
                updatePointCloud(message);
            }
        } catch (e) {
            console.error('Error handling message:', e);
        }
    };

    ws.onclose = () => {
        statusEl.textContent = 'Disconnected';
        statusEl.style.color = '#f00';
        // Only reconnect if it's the current topic (avoid race conditions on switch)
        if (ws.url.endsWith(currentTopic)) {
             setTimeout(() => connect(currentTopic), 1000);
        }
    };

    ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        ws.close();
    };
}

function parseBinaryPointCloud(buffer) {
    const view = new DataView(buffer);
    
    // Check Magic: 'LIDR'
    const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
    
    if (magic !== 'LIDR') {
        console.error('Invalid magic in binary payload:', magic);
        return null;
    }

    const version = view.getUint32(4, true);
    const timestamp = view.getFloat64(8, true);
    const count = view.getUint32(16, true);

    // Points start at offset 20
    const pointsBuffer = buffer.slice(20);
    const pointsArray = new Float32Array(pointsBuffer);

    return {
        binary: true,
        count: count,
        timestamp: timestamp,
        points: pointsArray
    };
}

function updatePointCloud(payload) {
    let count = 0;
    const positions = pointsObj.geometry.attributes.position.array;

    if (payload.binary) {
        count = payload.count;
        const limit = Math.min(count * 3, MAX_POINTS * 3);
        positions.set(payload.points.subarray(0, limit));
    } else {
        // Robust extraction from JSON
        let pointsData = null;
        
        if (Array.isArray(payload)) {
            pointsData = payload;
        } else if (payload.points && Array.isArray(payload.points)) {
            pointsData = payload.points;
        } else if (payload.data) {
            if (Array.isArray(payload.data)) {
                pointsData = payload.data;
            } else if (payload.data.points && Array.isArray(payload.data.points)) {
                pointsData = payload.data.points;
            }
        }

        if (pointsData && pointsData.length > 0) {
            // Optimization: if it's already a flat array (handled by backend or future-proofing)
            if (typeof pointsData[0] === 'number') {
                count = Math.floor(pointsData.length / 3);
                const limit = Math.min(count * 3, MAX_POINTS * 3);
                if (pointsData.subarray) {
                    positions.set(pointsData.subarray(0, limit));
                } else {
                    for (let i = 0; i < limit; i++) positions[i] = pointsData[i];
                }
            } else {
                // Standard nested array [[x,y,z], ...]
                count = pointsData.length;
                const limit = Math.min(count, MAX_POINTS);
                for (let i = 0; i < limit; i++) {
                    const pt = pointsData[i];
                    if (!pt) continue;
                    positions[i * 3] = pt[0];
                    positions[i * 3 + 1] = pt[1];
                    positions[i * 3 + 2] = pt[2];
                }
                count = limit;
            }
        }
    }

    // Always update count and draw range to support clearing the scene
    countEl.textContent = count;
    pointsObj.geometry.setDrawRange(0, count);

    if (count > 0) {
        // Optimize: only update the part of the buffer that actually contains data
        const attr = pointsObj.geometry.attributes.position;
        // Check for both updateRange and addUpdateRange for cross-version compatibility
        if (attr.addUpdateRange) {
            attr.addUpdateRange.offset = 0;
            attr.addUpdateRange.count = count * 3;
        } else if (attr.addUpdateRange) {
            attr.addUpdateRange.offset = 0;
            attr.addUpdateRange.count = count * 3;
        }
        attr.needsUpdate = true;
    }
}

// Start
fetchStatus();

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}
animate();

// --- Lidar Management Logic ---
const mgrBtn = document.getElementById('mgr-btn');
const mgrModal = document.getElementById('mgr-modal');
const closeMgr = document.getElementById('close-mgr');
const lidarList = document.getElementById('lidar-list');
const lidarForm = document.getElementById('lidar-form');
const pipelineSelect = document.getElementById('pipeline-select');
const reloadBtn = document.getElementById('reload-btn');

mgrBtn.onclick = () => {
    mgrModal.style.display = 'block';
    refreshLidarList();
};

closeMgr.onclick = () => {
    mgrModal.style.display = 'none';
};

window.onclick = (event) => {
    if (event.target == mgrModal) {
        mgrModal.style.display = 'none';
    }
};

async function refreshLidarList() {
    try {
        const res = await fetch('/lidars');
        const data = await res.json();
        
        // Update Pipeline Select
        pipelineSelect.innerHTML = '<option value="">None</option>';
        data.available_pipelines.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p;
            opt.textContent = p;
            pipelineSelect.appendChild(opt);
        });
        
        // Update Lidar List
        lidarList.innerHTML = '';
        data.lidars.forEach(lidar => {
            const div = document.createElement('div');
            div.className = 'lidar-item';
            
            div.innerHTML = `
                <div class="lidar-info">
                    <strong>${lidar.id}</strong>
                    <small>${lidar.mode === 'sim' ? 'Simulation' : 'Hardware'} • ${lidar.pipeline_name || 'No Pipeline'}</small>
                </div>
                <div>
                    <button class="edit-btn btn-outline">Edit</button>
                    <button class="delete-btn btn-danger">Delete</button>
                </div>
            `;
            
            div.querySelector('.edit-btn').onclick = () => {
                const form = lidarForm.elements;
                form.id.value = lidar.id;
                form.launch_args.value = lidar.launch_args;
                form.pipeline_name.value = lidar.pipeline_name || '';
                form.mode.value = lidar.mode;
                form.pcd_path.value = lidar.pcd_path || '';
                form.x.value = lidar.pose.x;
                form.y.value = lidar.pose.y;
                form.z.value = lidar.pose.z;
                form.roll.value = lidar.pose.roll;
                form.pitch.value = lidar.pose.pitch;
                form.yaw.value = lidar.pose.yaw;
            };

            div.querySelector('.delete-btn').onclick = async () => {
                if (!confirm(`Are you sure you want to delete ${lidar.id}?`)) return;
                try {
                    const res = await fetch(`/lidars/${lidar.id}`, { method: 'DELETE' });
                    const result = await res.json();
                    refreshLidarList();
                } catch (e) {
                    console.error('Error deleting lidar:', e);
                    alert('Failed to delete lidar');
                }
            };
            
            lidarList.appendChild(div);
        });
    } catch (e) {
        console.error('Error refreshing lidar list:', e);
    }
}

lidarForm.onsubmit = async (e) => {
    e.preventDefault();
    const formData = new FormData(lidarForm);
    const data = Object.fromEntries(formData.entries());
    
    // Numeric conversions
    ['x', 'y', 'z', 'roll', 'pitch', 'yaw'].forEach(k => data[k] = parseFloat(data[k]));
    
    try {
        const res = await fetch('/lidars', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await res.json();
        refreshLidarList();
    } catch (e) {
        console.error('Error saving lidar:', e);
        alert('Failed to save lidar configuration');
    }
};

reloadBtn.onclick = async () => {

    try {
        const res = await fetch('/lidars/reload', { method: 'POST' });
        const result = await res.json();
        mgrModal.style.display = 'none';
        // Give it a second to restart before refreshing topics
        setTimeout(location.reload(), 500);
    } catch (e) {
        console.error('Error reloading:', e);
        alert('Failed to reload configuration');
    }
};
