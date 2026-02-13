import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// Setup Scene
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000000);

// Setup Camera
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(15, 15, 15);
camera.lookAt(5, 5, 5);

// Setup Renderer
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
// Clear body to safely append (in case of re-runs or weird states)
// but keep #info
const existingCanvas = document.querySelector('canvas');
if (existingCanvas) existingCanvas.remove();
document.body.appendChild(renderer.domElement);

// Setup Controls
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(5, 5, 5);

// Grid Helper
const gridHelper = new THREE.GridHelper(20, 20, 0x444444, 0x222222);
gridHelper.position.set(0, -1, 0); // Optional: lower grid slightly
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
scene.add(pointsObj);

// WebSocket Connection
const statusEl = document.getElementById('status');
const countEl = document.getElementById('point-count');
const topicSelect = document.getElementById('topic-select');

let ws;
let currentTopic = '';

async function fetchTopics() {
    try {
        const response = await fetch('/status');
        const data = await response.json();
        const sensors = data.active_sensors || [];
        
        topicSelect.innerHTML = '';
        const topics = [];
        
        sensors.forEach(sensorId => {
            topics.push(`${sensorId}_raw_points`);
            topics.push(`${sensorId}_processed_points`);
        });

        topics.forEach(topic => {
            const option = document.createElement('option');
            option.value = topic;
            option.textContent = topic;
            topicSelect.appendChild(option);
        });

        if (topics.length > 0) {
            currentTopic = topics[0];
            connect(currentTopic);
        } else {
             statusEl.textContent = 'No active sensors';
        }
    } catch (e) {
        console.error('Error fetching status:', e);
        statusEl.textContent = 'Error fetching topics';
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

    ws.onopen = () => {
        statusEl.textContent = 'Connected';
        statusEl.style.color = '#0f0';
    };

    ws.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            // Handle both raw and processed structures
            updatePointCloud(message);
        } catch (e) {
            console.error('Error parsing message:', e);
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

function updatePointCloud(payload) {
    let pointsData = [];
    
    // Check if it's raw_points payload (has 'points' array)
    if (payload.points) {
        pointsData = payload.points;
    } 
    // Check if it's processed_points payload (might wrap it differently, based on previous code it was payload["data"]["points"])
    // But lidar_service.py sends: 
    // raw: { points: [...], count: N, ... }
    // processed: { points: [...], ... } (if the pipeline returns dict with points)
    // Update logic to be robust
    else if (payload.data && payload.data.points) {
         pointsData = payload.data.points;
    }

    if (!pointsData) return;

    const count = pointsData.length;
    countEl.textContent = count;

    const positions = pointsObj.geometry.attributes.position.array;
    
    for (let i = 0; i < count; i++) {
        const pt = pointsData[i];
        positions[i * 3] = pt[0];
        positions[i * 3 + 1] = pt[1];
        positions[i * 3 + 2] = pt[2];
    }
    
    pointsObj.geometry.setDrawRange(0, count);
    pointsObj.geometry.attributes.position.needsUpdate = true;
}

// Start
fetchTopics();
function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}
animate();
