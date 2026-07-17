// ==========================================================================
// MusiGram: Frontend JavaScript Application
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
    // State management
    let telegramStatus = 'disconnected';
    let socket = null;
    let categoriesList = [];
    
    // DOM Elements Cache
    const el = {
        tabs: document.querySelectorAll('.nav-btn'),
        tabPanes: document.querySelectorAll('.tab-pane'),
        statusDot: document.getElementById('status-dot'),
        statusText: document.getElementById('status-text'),
        
        // Forms
        downloadForm: document.getElementById('download-form'),
        tgSetupForm: document.getElementById('tg-setup-form'),
        tgVerifyForm: document.getElementById('tg-verify-form'),
        tgPasswordForm: document.getElementById('tg-password-form'),
        systemConfigForm: document.getElementById('system-config-form'),
        rcloneConfigForm: document.getElementById('rclone-config-form'),
        rcloneContent: document.getElementById('rclone_content'),
        
        // Form Inputs
        requestText: document.getElementById('request_text'),
        categorySelect: document.getElementById('category_select'),
        apiId: document.getElementById('api_id'),
        apiHash: document.getElementById('api_hash'),
        phone: document.getElementById('phone'),
        verifyCode: document.getElementById('verify_code'),
        verifyPassword: document.getElementById('verify_password'),
        botUsername: document.getElementById('bot_username'),
        basePath: document.getElementById('base_path'),
        
        // Containers & Badges
        downloadsContainer: document.getElementById('downloads-container'),
        categoriesRulesContainer: document.getElementById('categories-rules-container'),
        driveStatusBadge: document.getElementById('drive-status-badge'),
        toastContainer: document.getElementById('toast-container'),
        authPhoneVal: document.getElementById('auth-phone-val'),
        tgAuthorizedState: document.getElementById('tg-authorized-state'),
        emptyState: document.getElementById('empty-state'),
        
        // Buttons
        btnClearDownloads: document.getElementById('btn-clear-downloads'),
        btnChangeTgAccount: document.getElementById('btn-change-tg-account'),
        btnSyncLibrary: document.getElementById('btn-sync-library'),
        
        // Admin Auth Elements
        adminLoginForm: document.getElementById('admin-login-form'),
        adminLoginCard: document.getElementById('admin-login-card'),
        adminUsername: document.getElementById('admin_username'),
        adminPassword: document.getElementById('admin_password'),
        settingsContentWrapper: document.getElementById('settings-content-wrapper'),
    };

    // ==========================================================================
    // Tab Navigation
    // ==========================================================================
    function showAdminLoginView(showLogin) {
        if (showLogin) {
            el.adminLoginCard.classList.remove('hidden');
            el.settingsContentWrapper.classList.add('hidden');
        } else {
            el.adminLoginCard.classList.add('hidden');
            el.settingsContentWrapper.classList.remove('hidden');
        }
    }

    el.tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetPaneId = `tab-${tab.getAttribute('data-tab')}`;
            
            // Remove active states
            el.tabs.forEach(t => t.classList.remove('active'));
            el.tabPanes.forEach(pane => pane.classList.remove('active'));
            
            // Add active state to selected
            tab.classList.add('active');
            const targetPane = document.getElementById(targetPaneId);
            if (targetPane) targetPane.classList.add('active');
            
            // Reload configuration when opening settings tab
            if (tab.getAttribute('data-tab') === 'settings') {
                const token = localStorage.getItem('adminToken');
                if (token) {
                    showAdminLoginView(false);
                    loadSystemConfig();
                } else {
                    showAdminLoginView(true);
                }
            }
        });
    });

    // ==========================================================================
    // API Helpers
    // ==========================================================================
    async function apiRequest(endpoint, method = 'GET', body = null) {
        try {
            const headers = { 'Content-Type': 'application/json' };
            const token = localStorage.getItem('adminToken');
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            const options = { method, headers };
            if (body) options.body = JSON.stringify(body);
            
            const response = await fetch(endpoint, options);
            
            if (response.status === 401) {
                localStorage.removeItem('adminToken');
                showAdminLoginView(true);
                throw new Error('Sesión no autorizada o expirada.');
            }
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || 'Ha ocurrido un error en el servidor.');
            }
            return data;
        } catch (error) {
            console.error(`API Error (${endpoint}):`, error);
            showToast(error.message, 'error');
            throw error;
        }
    }

    // ==========================================================================
    // UI Helpers & Formatting
    // ==========================================================================
    function formatBytes(bytes, decimals = 2) {
        if (!bytes) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        let iconSvg = '';
        if (type === 'success') {
            iconSvg = `<svg class="toast-icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
        } else if (type === 'error') {
            iconSvg = `<svg class="toast-icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
        } else if (type === 'warning') {
            iconSvg = `<svg class="toast-icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>`;
        } else {
            iconSvg = `<svg class="toast-icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
        }
        
        toast.innerHTML = `
            ${iconSvg} 
            <span style="flex-grow: 1; padding-right: 8px;">${message}</span>
            <button class="toast-close-btn" style="background: none; border: none; color: white; cursor: pointer; opacity: 0.6; font-size: 1.2rem; padding: 0 4px; line-height: 1; display: flex; align-items: center; justify-content: center; transition: opacity 0.2s;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.6">&times;</button>
        `;
        el.toastContainer.appendChild(toast);
        
        const closeBtn = toast.querySelector('.toast-close-btn');
        const dismissToast = () => {
            if (toast.parentNode) {
                toast.classList.add('fade-out');
                toast.addEventListener('animationend', () => {
                    toast.remove();
                });
                // Fallback in case animation fails
                setTimeout(() => {
                    if (toast.parentNode) toast.remove();
                }, 350);
            }
        };

        closeBtn.addEventListener('click', dismissToast);
        
        // Remove toast after timeout
        setTimeout(dismissToast, 4000);
    }

    // ==========================================================================
    // WebSocket Client Logic (Real-time Downloads Feed)
    // ==========================================================================
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        console.log('Intentando conectar WebSocket:', wsUrl);
        socket = new WebSocket(wsUrl);
        
        socket.onopen = () => {
            console.log('WebSocket Conectado.');
            showToast('Conectado al servidor en tiempo real.', 'success');
            updateSystemStatus(); // Refresh status indicators
        };
        
        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'downloads_update') {
                    renderDownloadsList(data.downloads);
                }
            } catch (err) {
                console.error('Error procesando mensaje de WebSocket:', err);
            }
        };
        
        socket.onclose = () => {
            console.warn('WebSocket Desconectado. Reintentando en 3 segundos...');
            // Keep trying to reconnect
            setTimeout(connectWebSocket, 3000);
        };
        
        socket.onerror = (err) => {
            console.error('WebSocket Error:', err);
            socket.close();
        };
    }

    function renderDownloadsList(downloads) {
        // Clear except empty placeholder if empty
        const listItems = downloads.map(dl => {
            let statusBadgeClass = "badge-secondary";
            let statusLabel = dl.status;
            let progressDisplay = "";
            
            if (dl.status === "downloading") {
                statusBadgeClass = "badge-warning";
                statusLabel = "Descargando";
                progressDisplay = `
                    <div class="progress-section">
                        <div class="progress-bar-container">
                            <div class="progress-bar-fill" style="width: ${dl.progress}%"></div>
                        </div>
                        <div class="progress-details">
                            <span>${dl.progress}%</span>
                            <span>${formatBytes(dl.size)}</span>
                        </div>
                    </div>
                `;
            } else if (dl.status === "requested") {
                statusBadgeClass = "badge-info";
                statusLabel = "Solicitado";
            } else if (dl.status === "classifying") {
                statusBadgeClass = "badge-warning";
                statusLabel = "Organizando";
                progressDisplay = `
                    <div class="progress-section">
                        <div class="progress-bar-container">
                            <div class="progress-bar-fill" style="width: 100%"></div>
                        </div>
                        <div class="progress-details">
                            <span>Organizando en Drive...</span>
                        </div>
                    </div>
                `;
            } else if (dl.status === "completed") {
                statusBadgeClass = "badge-success";
                statusLabel = "Completado";
                progressDisplay = `
                    <div class="dest-path mt-2">
                        📁 Guardado en: ${dl.destination}
                    </div>
                `;
            } else if (dl.status === "failed") {
                statusBadgeClass = "badge-danger";
                statusLabel = "Fallido";
                progressDisplay = `
                    <div class="form-tip mt-1" style="color: #f87171;">
                        ❌ Error: ${dl.error}
                    </div>
                `;
            }

            let cancelBtn = "";
            if (dl.status === "downloading" || dl.status === "requested") {
                cancelBtn = `
                    <button class="btn btn-danger btn-sm btn-cancel-download" data-id="${dl.id}" style="padding: 4px 8px; font-size: 0.75rem; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px; background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #f87171; cursor: pointer; transition: var(--transition-smooth);">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="width:10px; height:10px;">
                            <line x1="18" y1="6" x2="6" y2="18"></line>
                            <line x1="6" y1="6" x2="18" y2="18"></line>
                        </svg>
                        Cancelar
                    </button>
                `;
            } else if (dl.status === "cancelled") {
                statusBadgeClass = "badge-danger";
                statusLabel = "Cancelado";
                progressDisplay = `
                    <div class="form-tip mt-1" style="color: #f87171;">
                        🛑 Cancelado por el usuario.
                    </div>
                `;
            } else if (dl.status === "skipped") {
                statusBadgeClass = "badge-warning";
                statusLabel = "Omitida";
                progressDisplay = `
                    <div class="form-tip mt-1" style="color: #fbbf24; font-weight: 500;">
                        ⚠️ ${dl.error || 'Canción duplicada en la biblioteca.'}
                    </div>
                `;
            }

            return `
                <div class="download-item" id="dl-${dl.id}">
                    <div class="download-meta-top">
                        <div style="flex-grow: 1; min-width: 0; padding-right: 12px;">
                            <h4 class="song-title" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${dl.filename}</h4>
                            <div class="song-info">
                                <span>🕒 ${dl.timestamp}</span>
                            </div>
                        </div>
                        <div style="display: flex; gap: 8px; align-items: center; flex-shrink: 0;">
                            ${cancelBtn}
                            <span class="badge ${statusBadgeClass}">${statusLabel}</span>
                            <span class="badge genre-tag">${dl.category}</span>
                        </div>
                    </div>
                    ${progressDisplay}
                </div>
            `;
        }).join('');
        
        // Remove empty state if we have items
        if (downloads.length > 0) {
            el.emptyState.classList.add('hidden');
            // Remove previous items, leave empty-state in DOM hidden
            const previousItems = el.downloadsContainer.querySelectorAll('.download-item');
            previousItems.forEach(item => item.remove());
            // Insert new items
            el.downloadsContainer.insertAdjacentHTML('beforeend', listItems);
        } else {
            // Remove previous items
            const previousItems = el.downloadsContainer.querySelectorAll('.download-item');
            previousItems.forEach(item => item.remove());
            el.emptyState.classList.remove('hidden');
        }

        // Attach event listeners to Cancel buttons
        el.downloadsContainer.querySelectorAll('.btn-cancel-download').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const dlId = btn.getAttribute('data-id');
                btn.disabled = true;
                btn.textContent = "Cancelando...";
                try {
                    await apiRequest('/api/downloads/cancel', 'POST', { download_id: dlId });
                    showToast('Petición de cancelación enviada.', 'info');
                } catch (err) {
                    btn.disabled = false;
                    btn.innerHTML = `
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="width:10px; height:10px;">
                            <line x1="18" y1="6" x2="6" y2="18"></line>
                            <line x1="6" y1="6" x2="18" y2="18"></line>
                        </svg>
                        Cancelar
                    `;
                }
            });
        });
    }

    // ==========================================================================
    // Application Initialization & Status Checking
    // ==========================================================================
    async function updateSystemStatus() {
        try {
            const data = await apiRequest('/api/status');
            telegramStatus = data.telegram_status;
            
            // 1. Update header status dot & text
            el.statusDot.className = 'status-dot';
            if (telegramStatus === 'authorized') {
                el.statusDot.classList.add('connected');
                el.statusText.textContent = `Conectado (@${data.bot_username})`;
            } else if (telegramStatus === 'connected') {
                el.statusDot.classList.add('waiting');
                el.statusText.textContent = 'Requiere Configuración';
            } else {
                el.statusDot.classList.add('disconnected');
                el.statusText.textContent = 'Telegram Desconectado';
            }
            
            // 2. Update category options in request dropdown
            categoriesList = data.categories;
            const currentSelected = el.categorySelect.value || 'Automático';
            el.categorySelect.innerHTML = '<option value="Automático">⚡ Clasificación Automática (ID3/Tags)</option>';
            categoriesList.forEach(folder => {
                if (folder !== 'General') { // General is fallback, let automatic handle it or map manually
                    el.categorySelect.insertAdjacentHTML('beforeend', `<option value="${folder}">${folder}</option>`);
                }
            });
            el.categorySelect.value = currentSelected;
            
            // 3. Update authorization settings card
            if (telegramStatus === 'authorized') {
                el.tgSetupForm.classList.add('hidden');
                el.tgVerifyForm.classList.add('hidden');
                el.tgPasswordForm.classList.add('hidden');
                el.tgAuthorizedState.classList.remove('hidden');
                // Fetch phone config details
                loadAuthDetails();
            } else if (telegramStatus === 'connected') {
                // Connected but unauthorized (requires code or password)
                // We keep current visible states unless they haven't submitted setup
            } else {
                // Unconfigured / Disconnected
                el.tgAuthorizedState.classList.add('hidden');
                el.tgSetupForm.classList.remove('hidden');
            }
            
            // 4. Update Drive path connection status
            el.driveStatusBadge.className = 'badge mt-1 ' + 
                (data.drive_status === 'connected' ? 'badge-success' : 'badge-danger');
            el.driveStatusBadge.textContent = data.drive_status === 'connected' ? 
                '📁 Unidad Conectada (Unidad G:)' : '❌ Unidad No Detectada (Comprueba tu disco G:)';
                
        } catch (err) {
            console.error('Error al actualizar estado:', err);
        }
    }

    async function loadAuthDetails() {
        try {
            const config = await apiRequest('/api/config');
            el.authPhoneVal.textContent = config.telegram.phone || 'Número no registrado';
        } catch (err) {
            console.error(err);
        }
    }

    // ==========================================================================
    // Settings Configuration Loader & Saver
    // ==========================================================================
    async function loadSystemConfig() {
        try {
            const data = await apiRequest('/api/config');
            
            el.botUsername.value = data.telegram.bot_username;
            el.basePath.value = data.storage.base_path;
            
            // Populate credentials form fields if not logged in
            if (telegramStatus !== 'authorized') {
                el.apiId.value = data.telegram.api_id || '';
                el.phone.value = data.telegram.phone || '';
            }
            
            // Render category keywords rows
            el.categoriesRulesContainer.innerHTML = '';
            const categories = data.storage.categories;
            
            Object.entries(categories).forEach(([category, keywords]) => {
                const keywordStr = keywords.join(', ');
                const rowHtml = `
                    <div class="category-rule-row">
                        <span class="category-rule-label">${category}</span>
                        <input type="text" class="category-keywords-input" data-category="${category}" value="${keywordStr}" placeholder="Separadas por comas">
                    </div>
                `;
                el.categoriesRulesContainer.insertAdjacentHTML('beforeend', rowHtml);
            });
            
            // Load Rclone configuration
            loadRcloneConfig();
            
        } catch (err) {
            showToast('Error al cargar configuración del sistema.', 'error');
        }
    }

    async function loadRcloneConfig() {
        try {
            const data = await apiRequest('/api/config/rclone');
            if (data && data.content) {
                el.rcloneContent.value = data.content;
            } else {
                el.rcloneContent.value = '';
            }
        } catch (err) {
            console.error('Error al cargar rclone.conf:', err);
        }
    }

    el.systemConfigForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Assemble categories object from inputs
        const categories = {};
        const keywordInputs = el.categoriesRulesContainer.querySelectorAll('.category-keywords-input');
        
        keywordInputs.forEach(input => {
            const category = input.getAttribute('data-category');
            const keywords = input.value.split(',')
                .map(kw => kw.trim())
                .filter(kw => kw !== '');
            categories[category] = keywords;
        });
        
        const body = {
            base_path: el.basePath.value.strip ? el.basePath.value.strip() : el.basePath.value,
            bot_username: el.botUsername.value.strip ? el.botUsername.value.strip() : el.botUsername.value,
            categories: categories
        };
        
        try {
            const res = await apiRequest('/api/config', 'POST', body);
            showToast(res.message, 'success');
            updateSystemStatus();
        } catch (err) {
            // Error is handled in apiRequest
        }
    });

    el.rcloneConfigForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const content = el.rcloneContent.value;
        try {
            const res = await apiRequest('/api/config/rclone', 'POST', { content });
            showToast(res.message, 'success');
        } catch (err) {
            // Error is handled in apiRequest
        }
    });

    el.adminLoginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = el.adminUsername.value.trim();
        const password = el.adminPassword.value.trim();
        
        try {
            const res = await apiRequest('/api/login', 'POST', { username, password });
            if (res.token) {
                localStorage.setItem('adminToken', res.token);
                showToast('Sesión de administrador iniciada.', 'success');
                showAdminLoginView(false);
                loadSystemConfig();
            }
        } catch (err) {
            // Handled
        }
    });

    el.btnSyncLibrary.addEventListener('click', async () => {
        el.btnSyncLibrary.disabled = true;
        const originalText = el.btnSyncLibrary.innerHTML;
        el.btnSyncLibrary.innerHTML = '🔄 Sincronizando biblioteca...';
        
        try {
            const res = await apiRequest('/api/library/sync', 'POST');
            showToast(res.message || 'Sincronización completada.', 'success');
        } catch (err) {
            console.error('Error al sincronizar biblioteca:', err);
        } finally {
            el.btnSyncLibrary.disabled = false;
            el.btnSyncLibrary.innerHTML = originalText;
        }
    });

    // ==========================================================================
    // Music Request Submission
    // ==========================================================================
    el.downloadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const text = el.requestText.value.trim();
        const category = el.categorySelect.value;
        
        if (!text) return;
        
        el.requestText.value = '';
        
        try {
            const res = await apiRequest('/api/download', 'POST', {
                request_text: text,
                category: category
            });
            showToast(res.message, 'success');
        } catch (err) {
            // Error is already alerted by helper
        }
    });

    // ==========================================================================
    // Telegram Multi-Step Authentication
    // ==========================================================================
    
    // Step 1: Submit Credentials & Request Verification Code
    el.tgSetupForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const body = {
            api_id: el.apiId.value.trim(),
            api_hash: el.apiHash.value.trim(),
            phone: el.phone.value.trim(),
            bot_username: el.botUsername.value.trim() || 'deezload2bot'
        };
        
        try {
            showToast('Conectando a Telegram y enviando código...', 'info');
            const res = await apiRequest('/api/setup', 'POST', body);
            
            if (res.status === 'code_sent') {
                showToast('Código enviado a tu cuenta de Telegram.', 'success');
                el.tgSetupForm.classList.add('hidden');
                el.tgVerifyForm.classList.remove('hidden');
                updateSystemStatus();
            } else {
                showToast(res.message || 'Error al conectar.', 'error');
            }
        } catch (err) {
            // Handled
        }
    });

    // Step 2: Submit Verification Code
    el.tgVerifyForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const body = {
            code: el.verifyCode.value.trim()
        };
        
        try {
            showToast('Verificando código...', 'info');
            const res = await apiRequest('/api/verify', 'POST', body);
            
            if (res.status === 'authorized') {
                showToast('¡Inicio de sesión exitoso!', 'success');
                el.tgVerifyForm.classList.add('hidden');
                updateSystemStatus();
            } else if (res.status === 'password_required') {
                showToast('Verificación en dos pasos (2FA) requerida.', 'warning');
                el.tgVerifyForm.classList.add('hidden');
                el.tgPasswordForm.classList.remove('hidden');
            } else {
                showToast(res.message || 'Código incorrecto.', 'error');
            }
        } catch (err) {
            // Handled
        }
    });

    // Step 3: Submit 2FA Password
    el.tgPasswordForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const body = {
            password: el.verifyPassword.value.trim()
        };
        
        try {
            showToast('Verificando contraseña...', 'info');
            const res = await apiRequest('/api/verify-password', 'POST', body);
            
            if (res.status === 'authorized') {
                showToast('¡Inicio de sesión exitoso con 2FA!', 'success');
                el.tgPasswordForm.classList.add('hidden');
                updateSystemStatus();
            } else {
                showToast(res.message || 'Contraseña incorrecta.', 'error');
            }
        } catch (err) {
            // Handled
        }
    });

    // Logout/Change Telegram Account
    el.btnChangeTgAccount.addEventListener('click', () => {
        if (confirm('¿Estás seguro de que deseas cerrar sesión en esta cuenta de Telegram? Se restablecerán tus credenciales locales.')) {
            el.tgAuthorizedState.classList.add('hidden');
            el.tgSetupForm.classList.remove('hidden');
            el.apiId.value = '';
            el.apiHash.value = '';
            el.phone.value = '';
            el.verifyCode.value = '';
            el.verifyPassword.value = '';
            
            // Update status by sending empty credentials to reset
            apiRequest('/api/setup', 'POST', {
                api_id: '',
                api_hash: '',
                phone: '',
                bot_username: el.botUsername.value.trim() || 'deezload2bot'
            }).then(() => {
                updateSystemStatus();
                showToast('Sesión de Telegram cerrada.', 'info');
            }).catch(console.error);
        }
    });

    // ==========================================================================
    // Clear Finished Downloads
    // ==========================================================================
    el.btnClearDownloads.addEventListener('click', async () => {
        try {
            await apiRequest('/api/downloads/clear', 'POST');
            showToast('Historial limpiado.', 'success');
        } catch (err) {
            // Handled
        }
    });

    // ==========================================================================
    // Kickstart Application
    // ==========================================================================
    updateSystemStatus();
    connectWebSocket();
});
