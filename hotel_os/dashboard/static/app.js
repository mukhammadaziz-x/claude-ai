// ============================================================
// HotelOS — Dashboard Application JavaScript
// Handles: Auth, WebSocket, Tabs, Rooms, Orders, Maintenance,
//          Housekeeping, Modals, Live Feed
// ============================================================

'use strict';

// ── State ──────────────────────────────────────────────────
const State = {
    token:    null,
    ws:       null,
    rooms:    [],
    orders:   [],
    requests: [],
    queue:    [],
    guests:   [],
};

// ── API Base URLs ──────────────────────────────────────────
const API = {
    dashboard:     'http://localhost:8000',
    reception:     'http://localhost:8001',
    housekeeping:  'http://localhost:8002',
    roomService:   'http://localhost:8003',
    maintenance:   'http://localhost:8004',
};

// ── DOM helpers ────────────────────────────────────────────
const $  = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

// ── Fetch helper ───────────────────────────────────────────
async function apiFetch(url, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (State.token) headers['Authorization'] = `Bearer ${State.token}`;
    const resp = await fetch(url, { ...options, headers });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(typeof err.detail === 'string' ? err.detail
            : err.detail?.message || JSON.stringify(err.detail));
    }
    return resp.json();
}

// ── Toast ──────────────────────────────────────────────────
function toast(message, type = 'info') {
    const icons = { success:'check-circle', error:'times-circle',
                    info:'info-circle', warning:'exclamation-triangle' };
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<i class="fas fa-${icons[type]}"></i> ${message}`;
    $('toastContainer').appendChild(el);
    setTimeout(() => { el.style.opacity='0'; el.style.transform='translateX(40px)';
                       setTimeout(() => el.remove(), 300); }, 4000);
}

// ── Tab switching ──────────────────────────────────────────
function initTabs() {
    $$('.nav-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            $$('.nav-tab').forEach(t => t.classList.remove('active'));
            $$('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            $(`tab-${tab.dataset.tab}`).classList.add('active');
            refreshCurrentTab(tab.dataset.tab);
        });
    });
}

async function refreshCurrentTab(tab) {
    if (tab === 'overview')     await loadOverview();
    if (tab === 'rooms')        await loadRooms();
    if (tab === 'orders')       await loadOrders();
    if (tab === 'maintenance')  await loadMaintenance();
    if (tab === 'housekeeping') await loadHousekeeping();
}

// ============================================================
// AUTH
// ============================================================
function initAuth() {
    $('loginForm').addEventListener('submit', async e => {
        e.preventDefault();
        $('loginError').textContent = '';
        try {
            const data = await apiFetch(`${API.dashboard}/auth/login`, {
                method: 'POST',
                body: JSON.stringify({
                    username: $('loginUsername').value.trim(),
                    password: $('loginPassword').value,
                }),
            });
            State.token = data.access_token;
            localStorage.setItem('hotelos_token', State.token);
            showDashboard();
        } catch (err) {
            $('loginError').textContent = err.message;
        }
    });

    $('logoutBtn').addEventListener('click', () => {
        State.token = null;
        localStorage.removeItem('hotelos_token');
        if (State.ws) State.ws.close();
        $('dashboard').style.display = 'none';
        $('loginOverlay').style.display = 'flex';
    });

    // Auto-login from localStorage
    const saved = localStorage.getItem('hotelos_token');
    if (saved) { State.token = saved; showDashboard(); }
}

async function showDashboard() {
    $('loginOverlay').style.display = 'none';
    $('dashboard').style.display    = 'block';
    await loadOverview();
    connectWebSocket();
}


// ============================================================
// WEBSOCKET
// ============================================================
function connectWebSocket() {
    const wsUrl = `ws://localhost:8000/ws?token=${State.token}`;
    State.ws = new WebSocket(wsUrl);

    State.ws.onopen = () => {
        updateWsStatus(true);
        toast('Connected to live system', 'success');
    };

    State.ws.onmessage = e => {
        try {
            const msg = JSON.parse(e.data);
            handleBrokerMessage(msg);
        } catch { /* ignore malformed */ }
    };

    State.ws.onerror = () => updateWsStatus(false);

    State.ws.onclose = () => {
        updateWsStatus(false);
        // Reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
    };

    // Heartbeat ping every 20s
    setInterval(() => {
        if (State.ws && State.ws.readyState === WebSocket.OPEN) {
            State.ws.send('ping');
        }
    }, 20000);
}

function updateWsStatus(connected) {
    const wsEl  = $('wsStatus');
    const dotEl = $('wsDot');
    const lblEl = $('wsLabel');
    if (connected) {
        wsEl.className  = 'ws-status connected';
        lblEl.textContent = 'Live';
    } else {
        wsEl.className  = 'ws-status disconnected';
        lblEl.textContent = 'Reconnecting...';
    }
}

function handleBrokerMessage(msg) {
    const ch   = msg.channel;
    const data = msg.data || {};

    // Initial snapshot
    if (ch === 'snapshot') {
        State.rooms    = data.rooms    || [];
        State.orders   = data.orders   || [];
        State.requests = data.requests || [];
        State.queue    = data.queue    || [];
        State.guests   = data.guests   || [];
        renderAll();
        return;
    }

    // Live events
    switch (ch) {
        case 'guest.checked_in':
            addFeedItem('checkin', 'fa-user-plus',
                `<b>${data.guest_name}</b> checked in → Room <b>${data.room_number}</b>`, 'green');
            toast(`Check-in: ${data.guest_name} → Room ${data.room_number}`, 'success');
            refreshRooms();
            break;
        case 'guest.checked_out':
            addFeedItem('checkout', 'fa-user-minus',
                `<b>${data.guest_name}</b> checked out from Room <b>${data.room_number}</b> | $${data.grand_total}`, 'purple');
            toast(`Check-out: ${data.guest_name} | Total: $${data.grand_total}`, 'info');
            refreshRooms();
            break;
        case 'room.status_changed':
            addFeedItem('housekeep', 'fa-broom',
                `Room <b>${data.room_number}</b> status → <b>${data.status}</b>`, 'blue');
            refreshRooms();
            refreshHousekeeping();
            updateStats();
            break;
        case 'room.vacated':
            addFeedItem('housekeep', 'fa-door-open',
                `Room <b>${data.room_number}</b> vacated — added to cleaning queue`, 'yellow');
            refreshRooms();
            break;
        case 'order.new':
            addFeedItem('order', 'fa-utensils',
                `New order <b>#${data.order_id}</b> for Room <b>${data.room_number}</b> | $${data.total}`, 'orange');
            toast(`New order #${data.order_id} for Room ${data.room_number}`, 'info');
            refreshOrders();
            break;
        case 'order.state_changed':
            addFeedItem('order', 'fa-truck',
                `Order <b>#${data.order_id}</b> → <b>${data.new_status}</b>`, 'orange');
            refreshOrders();
            break;
        case 'maintenance.new_request':
            addFeedItem('maint', 'fa-exclamation-triangle',
                `🔧 Room <b>${data.room_number}</b>: ${data.description} [<b>${data.urgency}</b>]`, 'red');
            toast(`Maintenance: Room ${data.room_number} — ${data.urgency}`, 'warning');
            refreshMaintenance();
            break;
        case 'maintenance.status_changed':
            addFeedItem('maint', 'fa-tools',
                `Request <b>${data.request_id}</b> → <b>${data.status}</b>
                 ${data.assigned_to ? '· ' + data.assigned_to : ''}`, 'red');
            refreshMaintenance();
            break;
    }
}

// ============================================================
// FEED
// ============================================================
const colourMap = {
    green: '#22c55e', purple: '#7c3aed', blue: '#3b82f6',
    yellow: '#d97706', orange: '#f97316', red: '#ef4444',
};

function addFeedItem(cls, icon, html, colour) {
    const feed = $('activityFeed');
    // Remove empty state
    const empty = feed.querySelector('.feed-empty');
    if (empty) empty.remove();

    const now  = new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
    const item = document.createElement('div');
    item.className = `feed-item ${cls}`;
    item.style.borderLeftColor = colourMap[colour] || '#7c3aed';
    item.innerHTML = `
        <i class="fas ${icon}" style="color:${colourMap[colour]}"></i>
        <span>${html}</span>
        <span class="feed-time">${now}</span>`;
    feed.insertBefore(item, feed.firstChild);

    // Keep max 50 items
    while (feed.children.length > 50) feed.removeChild(feed.lastChild);
}

$('clearFeedBtn') && document.addEventListener('DOMContentLoaded', () => {
    $('clearFeedBtn').addEventListener('click', () => {
        $('activityFeed').innerHTML =
            '<div class="feed-empty"><i class="fas fa-satellite-dish"></i><p>Waiting for events...</p></div>';
    });
});


// ============================================================
// RENDER FUNCTIONS
// ============================================================
function renderAll() {
    renderRoomMap();
    renderRoomsGrid();
    renderOrders();
    renderMaintenance();
    renderHousekeeping();
    updateStats();
}

// ── Stats ─────────────────────────────────────────────────
function updateStats() {
    const rooms = State.rooms;
    $('statClean').textContent    = rooms.filter(r => r.status === 'Clean').length;
    $('statOccupied').textContent = rooms.filter(r => r.status === 'Occupied').length;
    $('statDirty').textContent    = rooms.filter(r =>
        r.status === 'Dirty' || r.status === 'Being Cleaned').length;
    $('statMaint').textContent    = rooms.filter(r => r.status === 'Maintenance').length;
    $('statOrders').textContent   = State.orders.filter(
        o => o.status !== 'Delivered').length;
}

// ── Room Map ───────────────────────────────────────────────
function renderRoomMap() {
    const map = $('roomMap');
    if (!map) return;
    map.innerHTML = '';
    const statusClass = {
        'Clean': 'clean', 'Occupied': 'occupied',
        'Dirty': 'dirty', 'Being Cleaned': 'being_cleaned', 'Maintenance': 'maintenance',
    };
    State.rooms.forEach(room => {
        const cell = document.createElement('div');
        cell.className = `room-cell ${statusClass[room.status] || 'clean'}`;
        cell.title = `Room ${room.number} · ${room.room_type} · ${room.status}` +
                     (room.guest_name ? ` · ${room.guest_name}` : '');
        cell.innerHTML = `<span class="room-num">${room.number}</span>
                          <span class="room-type-tag">${room.room_type.substring(0,3)}</span>`;
        map.appendChild(cell);
    });
}

// ── Rooms Grid ─────────────────────────────────────────────
function renderRoomsGrid() {
    const grid = $('roomsGrid');
    if (!grid) return;
    if (!State.rooms.length) {
        grid.innerHTML = '<div class="empty-state"><i class="fas fa-bed"></i><p>No rooms loaded</p></div>';
        return;
    }
    const pillMap = {
        'Clean': 'pill-clean', 'Occupied': 'pill-occupied',
        'Dirty': 'pill-dirty', 'Being Cleaned': 'pill-being_cleaned', 'Maintenance': 'pill-maintenance',
    };
    const statusIcon = {
        'Clean': 'fa-check-circle', 'Occupied': 'fa-user',
        'Dirty': 'fa-exclamation', 'Being Cleaned': 'fa-broom', 'Maintenance': 'fa-tools',
    };
    grid.innerHTML = State.rooms.map(room => `
        <div class="room-card">
            <div class="room-card-top">
                <span class="room-number">${room.number}</span>
                <span class="room-type-badge">${room.room_type}</span>
            </div>
            <div class="room-card-body">
                <span class="room-status-pill ${pillMap[room.status] || 'pill-clean'}">
                    <i class="fas ${statusIcon[room.status] || 'fa-circle'}"></i>
                    ${room.status}
                </span>
                <div class="room-guest">
                    ${room.guest_name
                        ? `<i class="fas fa-user"></i> ${room.guest_name}`
                        : `<span style="color:var(--text-light)">Vacant</span>`}
                </div>
                <div class="room-rate">Floor ${room.floor} &nbsp;·&nbsp; $${room.rate_per_night}/night</div>
            </div>
        </div>`).join('');
}

// ── Orders ─────────────────────────────────────────────────
function renderOrders() {
    const list = $('ordersList');
    if (!list) return;
    if (!State.orders.length) {
        list.innerHTML = '<div class="empty-state"><i class="fas fa-utensils"></i><p>No orders yet</p></div>';
        return;
    }
    const states = ['Received', 'Preparing', 'Out for Delivery', 'Delivered'];
    list.innerHTML = State.orders.map(order => {
        const idx = states.indexOf(order.status);
        const steps = states.map((s, i) => `
            <span class="progress-step ${i < idx ? 'done' : i === idx ? 'active' : ''}">
                ${s}
            </span>
            ${i < states.length - 1 ? '<i class="fas fa-chevron-right progress-arrow"></i>' : ''}
        `).join('');
        const items = order.items.map(it =>
            `<div class="order-item-line">${it.quantity}× ${it.name} — $${it.subtotal}</div>`).join('');
        return `
        <div class="order-card">
            <div class="order-card-header">
                <span class="order-id"><i class="fas fa-hashtag"></i> ${order.order_id}</span>
                <span class="order-room-badge"><i class="fas fa-door-open"></i> Room ${order.room_number}</span>
            </div>
            <div class="order-card-body">
                <div class="order-items">${items}</div>
                <div class="order-total">Total: $${order.total}</div>
            </div>
            <div class="order-card-footer">
                <div class="order-progress">${steps}</div>
                ${order.status !== 'Delivered'
                    ? `<button class="btn btn-sm btn-primary" onclick="advanceOrder('${order.order_id}')">
                           <i class="fas fa-arrow-right"></i> Advance
                       </button>`
                    : '<span style="color:var(--green);font-size:.8rem;font-weight:600"><i class="fas fa-check"></i> Done</span>'}
            </div>
        </div>`;
    }).join('');
}

// ── Maintenance ────────────────────────────────────────────
function renderMaintenance() {
    const list = $('maintenanceList');
    if (!list) return;
    if (!State.requests.length) {
        list.innerHTML = '<div class="empty-state"><i class="fas fa-tools"></i><p>No maintenance requests</p></div>';
        return;
    }
    const statusClass = { 'Open': 'status-Open', 'In Progress': 'status-In_Progress', 'Resolved': 'status-Resolved' };
    list.innerHTML = State.requests.map(req => `
        <div class="maint-card">
            <div class="maint-left">
                <div class="maint-id">${req.request_id}</div>
                <div class="maint-desc">${req.description}</div>
                <div class="maint-meta">
                    <span class="urgency-badge urgency-${req.urgency}">${req.urgency}</span>
                    <span class="maint-room"><i class="fas fa-door-open"></i> Room ${req.room_number}</span>
                    ${req.assigned_to
                        ? `<span class="maint-assignee"><i class="fas fa-user-hard-hat"></i> ${req.assigned_to}</span>`
                        : ''}
                </div>
            </div>
            <span class="maint-status ${statusClass[req.status] || ''}">${req.status}</span>
        </div>`).join('');
}

// ── Housekeeping ───────────────────────────────────────────
function renderHousekeeping() {
    const list = $('housekeepingList');
    if (!list) return;
    if (!State.queue.length) {
        list.innerHTML = '<div class="empty-state"><i class="fas fa-broom"></i><p>Cleaning queue is empty</p></div>';
        return;
    }
    list.innerHTML = State.queue.map(task => `
        <div class="hk-card">
            <div class="hk-left">
                <span class="hk-room-num">${task.room_number}</span>
                <div class="hk-info">
                    <strong>${task.room_type}</strong> · Floor ${task.floor}<br>
                    Status: <strong>${task.status}</strong>
                    ${task.assigned_to ? ` · ${task.assigned_to}` : ''}
                </div>
            </div>
            <div class="hk-actions">
                ${task.status === 'Pending'
                    ? `<button class="btn btn-sm btn-primary" onclick="startCleaning(${task.room_number})">
                           <i class="fas fa-play"></i> Start
                       </button>`
                    : ''}
                ${task.status === 'Being Cleaned'
                    ? `<button class="btn btn-sm btn-success" onclick="completeCleaning(${task.room_number})">
                           <i class="fas fa-check"></i> Done
                       </button>`
                    : ''}
            </div>
        </div>`).join('');
}


// ============================================================
// DATA LOADERS
// ============================================================
async function loadOverview() {
    try {
        const snap = await apiFetch(`${API.dashboard}/api/snapshot`);
        State.rooms    = snap.rooms    || [];
        State.orders   = snap.orders   || [];
        State.requests = snap.requests || [];
        State.queue    = snap.queue    || [];
        State.guests   = snap.guests   || [];
        renderAll();
    } catch (e) { toast('Could not load overview: ' + e.message, 'error'); }
}
async function loadRooms() {
    try { State.rooms = await apiFetch(`${API.dashboard}/api/rooms`); renderRoomsGrid(); updateStats(); }
    catch (e) { toast('Could not load rooms: ' + e.message, 'error'); }
}
async function loadOrders() {
    try { State.orders = await apiFetch(`${API.dashboard}/api/orders`); renderOrders(); }
    catch (e) { toast('Could not load orders: ' + e.message, 'error'); }
}
async function loadMaintenance() {
    try { State.requests = await apiFetch(`${API.dashboard}/api/requests`); renderMaintenance(); }
    catch (e) { toast('Could not load maintenance: ' + e.message, 'error'); }
}
async function loadHousekeeping() {
    try { State.queue = await apiFetch(`${API.dashboard}/api/queue`); renderHousekeeping(); }
    catch (e) { toast('Could not load queue: ' + e.message, 'error'); }
}

// Lightweight refreshers (called by WS events)
const refreshRooms       = loadRooms;
const refreshOrders      = loadOrders;
const refreshMaintenance = loadMaintenance;
const refreshHousekeeping = loadHousekeeping;

// ============================================================
// ACTIONS
// ============================================================

// ── Advance order ─────────────────────────────────────────
async function advanceOrder(orderId) {
    try {
        await apiFetch(`${API.roomService}/orders/advance`, {
            method: 'POST', body: JSON.stringify({ order_id: orderId }),
        });
        toast(`Order #${orderId} advanced`, 'success');
        await loadOrders();
    } catch (e) { toast(e.message, 'error'); }
}

// ── Start cleaning ─────────────────────────────────────────
async function startCleaning(roomNumber) {
    const housekeeper = prompt(`Housekeeper name for Room ${roomNumber}?`, 'Housekeeper 1');
    if (!housekeeper) return;
    try {
        await apiFetch(`${API.housekeeping}/cleaning/start`, {
            method: 'POST',
            body: JSON.stringify({ room_number: roomNumber, housekeeper }),
        });
        toast(`Cleaning started for Room ${roomNumber}`, 'success');
        await loadHousekeeping();
    } catch (e) { toast(e.message, 'error'); }
}

// ── Complete cleaning ──────────────────────────────────────
async function completeCleaning(roomNumber) {
    try {
        await apiFetch(`${API.housekeeping}/cleaning/complete`, {
            method: 'POST', body: JSON.stringify({ room_number: roomNumber }),
        });
        toast(`Room ${roomNumber} marked Clean ✓`, 'success');
        await loadHousekeeping();
        await loadRooms();
    } catch (e) { toast(e.message, 'error'); }
}

// ============================================================
// MODALS
// ============================================================
function openModal(id)  { $(id).classList.add('open'); }
function closeModal(id) { $(id).classList.remove('open'); }

function initModals() {
    // Close buttons
    $$('.modal-close').forEach(btn => {
        btn.addEventListener('click', () => closeModal(btn.dataset.modal));
    });
    // Click outside to close
    $$('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', e => {
            if (e.target === overlay) overlay.classList.remove('open');
        });
    });

    // Open buttons
    $('checkInBtn')   && $('checkInBtn').addEventListener('click',  () => openModal('checkInModal'));
    $('checkOutBtn')  && $('checkOutBtn').addEventListener('click', () => openModal('checkOutModal'));
    $('newOrderBtn')  && $('newOrderBtn').addEventListener('click', () => openModal('newOrderModal'));
    $('newRequestBtn')&& $('newRequestBtn').addEventListener('click',() => openModal('newRequestModal'));

    // Check In form
    $('checkInForm').addEventListener('submit', async e => {
        e.preventDefault();
        try {
            const body = {
                guest_name:       $('ciName').value.trim(),
                room_type:        $('ciType').value,
                nights:           parseInt($('ciNights').value),
                floor_preference: $('ciFloor').value ? parseInt($('ciFloor').value) : null,
                proximity_pref:   $('ciProximity').value || null,
                discount_pct:     parseFloat($('ciDiscount').value) || 0,
            };
            const res = await apiFetch(`${API.reception}/checkin`, { method:'POST', body: JSON.stringify(body) });
            toast(`✓ Checked in: ${res.guest_name} → Room ${res.room_number}`, 'success');
            closeModal('checkInModal');
            $('checkInForm').reset();
            await loadRooms();
        } catch (e) { toast(e.message, 'error'); }
    });

    // Check Out form
    $('checkOutForm').addEventListener('submit', async e => {
        e.preventDefault();
        $('billResult').style.display = 'none';
        try {
            const body = {
                room_number:    parseInt($('coRoom').value),
                early_checkout: $('coEarly').checked,
                late_fee:       parseFloat($('coLateFee').value) || 0,
            };
            const res = await apiFetch(`${API.reception}/checkout`, { method:'POST', body: JSON.stringify(body) });
            const bill = res.bill;
            let rows = bill.breakdown.map(b =>
                `<tr><td>${b.description}</td><td class="bill-amount">$${b.amount.toFixed(2)}</td></tr>`
            ).join('');
            $('billResult').style.display = 'block';
            $('billResult').innerHTML = `
                <hr style="margin-bottom:12px">
                <strong>Bill for ${bill.guest_name}</strong>
                <table class="bill-table" style="margin-top:8px">
                    ${rows}
                    <tr><td><strong>Grand Total</strong></td>
                        <td class="bill-amount"><strong>$${bill.grand_total.toFixed(2)}</strong></td></tr>
                </table>`;
            toast(`Checked out | Total: $${bill.grand_total.toFixed(2)}`, 'success');
            await loadRooms();
        } catch (e) { toast(e.message, 'error'); }
    });

    // Add order item row
    $('addItemBtn') && $('addItemBtn').addEventListener('click', () => {
        const row = document.createElement('div');
        row.className = 'order-item-row';
        row.innerHTML = `
            <input type="text"   placeholder="Item name"  class="item-name"  required>
            <input type="number" placeholder="Qty"        class="item-qty"   value="1" min="1">
            <input type="number" placeholder="Price $"    class="item-price" step="0.01" min="0.01">
            <button type="button" class="remove-item-btn"><i class="fas fa-times"></i></button>`;
        row.querySelector('.remove-item-btn').addEventListener('click', () => row.remove());
        $('orderItems').appendChild(row);
    });

    // Remove first item row button
    document.addEventListener('click', e => {
        if (e.target.closest('.remove-item-btn')) {
            e.target.closest('.order-item-row').remove();
        }
    });

    // New Order form
    $('newOrderForm').addEventListener('submit', async e => {
        e.preventDefault();
        try {
            const rows = $$('#orderItems .order-item-row');
            const items = Array.from(rows).map(row => ({
                name:     row.querySelector('.item-name').value.trim(),
                quantity: parseInt(row.querySelector('.item-qty').value),
                price:    parseFloat(row.querySelector('.item-price').value),
            }));
            const body = { room_number: parseInt($('orRoom').value), items };
            const res = await apiFetch(`${API.roomService}/orders`, { method:'POST', body: JSON.stringify(body) });
            toast(`Order #${res.order.order_id} placed for Room ${res.order.room_number}`, 'success');
            closeModal('newOrderModal');
            $('newOrderForm').reset();
            await loadOrders();
        } catch (e) { toast(e.message, 'error'); }
    });

    // New Maintenance form
    $('newRequestForm').addEventListener('submit', async e => {
        e.preventDefault();
        try {
            const body = {
                room_number: parseInt($('mrRoom').value),
                description: $('mrDesc').value.trim(),
                urgency:     $('mrUrgency').value,
            };
            const res = await apiFetch(`${API.maintenance}/requests`, { method:'POST', body: JSON.stringify(body) });
            toast(`Request ${res.request.request_id} submitted`, 'success');
            closeModal('newRequestModal');
            $('newRequestForm').reset();
            await loadMaintenance();
        } catch (e) { toast(e.message, 'error'); }
    });
}

// ============================================================
// INIT
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    initAuth();
    initTabs();
    initModals();

    $('clearFeedBtn') && $('clearFeedBtn').addEventListener('click', () => {
        $('activityFeed').innerHTML =
            '<div class="feed-empty"><i class="fas fa-satellite-dish"></i><p>Waiting for events...</p></div>';
    });
});
