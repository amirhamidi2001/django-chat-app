// ===== Django injected data =====
const currentUser = CHAT_DATA.currentUser;
const otherUser = CHAT_DATA.otherUser;
const uploadUrl = CHAT_DATA.uploadUrl;
const csrfToken = CHAT_DATA.csrfToken;

// WebSocket URL
const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${protocol}//${location.host}/ws/chat/${otherUser}/`;
let chatSocket = null;

// DOM elements
const messagesContainer = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const chatForm = document.getElementById('chat-form');
const connectionStatus = document.getElementById('connection-status');
const onlineStatusIndicator = document.getElementById('online-status-indicator');
const lastSeenText = document.getElementById('last-seen-text');
const typingIndicator = document.getElementById('typing-indicator');
const loadMoreIndicator = document.getElementById('load-more-indicator');
const initialLoading = document.getElementById('initial-loading');
const endOfMessages = document.getElementById('end-of-messages');

// File upload elements
const fileInput = document.getElementById('file-input');
const filePreview = document.getElementById('file-preview');
const previewFilename = document.getElementById('preview-filename');
const previewFilesize = document.getElementById('preview-filesize');
const removeFileBtn = document.getElementById('remove-file');
const uploadProgress = document.getElementById('upload-progress');
const progressFill = document.getElementById('progress-fill');
const progressPercent = document.getElementById('progress-percent');

// NEW: Notification elements
const notificationBanner = document.getElementById('notification-banner');
const notificationToggle = document.getElementById('notification-toggle');
const notificationIcon = document.getElementById('notification-icon');
const notificationText = document.getElementById('notification-text');
const btnAllow = document.getElementById('btn-allow-notifications');
const btnDismiss = document.getElementById('btn-dismiss-notifications');
const notificationSound = document.getElementById('notification-sound');

// State management
let typingTimer = null;
let isCurrentlyTyping = false;
const TYPING_TIMER_LENGTH = 3000;

let currentOffset = 0;
let hasMoreMessages = true;
let isLoadingMore = false;
let isInitialLoad = true;
let totalMessageCount = 0;
const SCROLL_THRESHOLD = 100;

const unreadMessageIds = new Set();
const intersectionObserver = createIntersectionObserver();

let selectedFile = null;

// NEW: Notification state
let notificationsEnabled = false;
let soundEnabled = true;
let isPageVisible = true;
let unreadCount = 0;
const originalTitle = document.title;

// ========================================================================
// NEW: NOTIFICATION FUNCTIONS
// ========================================================================

/**
 * Check if notifications are supported
 */
function notificationsSupported() {
    return 'Notification' in window;
}

/**
 * Get notification permission status
 */
function getNotificationPermission() {
    if (!notificationsSupported()) return 'unsupported';
    return Notification.permission;
}

/**
 * Request notification permission
 */
async function requestNotificationPermission() {
    if (!notificationsSupported()) {
        alert('Your browser does not support notifications');
        return false;
    }

    try {
        const permission = await Notification.requestPermission();
        updateNotificationUI();

        if (permission === 'granted') {
            notificationsEnabled = true;
            saveNotificationPreference(true);
            showTestNotification();
            return true;
        } else {
            notificationsEnabled = false;
            return false;
        }
    } catch (error) {
        console.error('Error requesting notification permission:', error);
        return false;
    }
}

/**
 * Show a browser notification
 */
function showNotification(title, options = {}) {
    if (!notificationsEnabled || isPageVisible) {
        return null;
    }

    if (getNotificationPermission() !== 'granted') {
        return null;
    }

    const defaultOptions = {
        icon: '/static/chat/notification-icon.png',  // Add your icon
        badge: '/static/chat/notification-badge.png',
        vibrate: [200, 100, 200],
        requireInteraction: false,
        ...options
    };

    try {
        const notification = new Notification(title, defaultOptions);

        // Click to focus window
        notification.onclick = function () {
            window.focus();
            notification.close();
        };

        // Auto-close after 5 seconds
        setTimeout(() => notification.close(), 5000);

        return notification;
    } catch (error) {
        console.error('Error showing notification:', error);
        return null;
    }
}

/**
 * Show test notification
 */
function showTestNotification() {
    showNotification('Notifications Enabled! 🎉', {
        body: 'You will now receive notifications from this chat',
        tag: 'test-notification'
    });
}

/**
 * Handle new message notification
 */
function handleNewMessageNotification(data) {
    // Don't notify for own messages
    if (data.sender === currentUser) {
        return;
    }

    // Only notify if page is not visible
    if (isPageVisible) {
        return;
    }

    // Increment unread count
    unreadCount++;
    updatePageTitle();

    // Play sound if enabled
    if (soundEnabled) {
        playNotificationSound();
    }

    // Show browser notification
    let body = data.message;

    // Format file messages
    if (data.has_file) {
        if (data.is_image) {
            body = '📷 Sent a photo';
            if (data.message) {
                body += ': ' + data.message;
            }
        } else {
            body = '📎 Sent a file: ' + data.file_name;
        }
    }

    // Truncate long messages
    if (body.length > 100) {
        body = body.substring(0, 97) + '...';
    }

    showNotification(`New message from ${otherUser}`, {
        body: body,
        tag: 'new-message-' + data.message_id,
    });
}

/**
 * Play notification sound
 */
function playNotificationSound() {
    if (!soundEnabled) return;

    try {
        notificationSound.currentTime = 0;
        notificationSound.play().catch(e => {
            console.log('Could not play sound:', e);
        });
    } catch (error) {
        console.error('Error playing sound:', error);
    }
}

/**
 * Update page title with unread count
 */
function updatePageTitle() {
    if (unreadCount > 0 && !isPageVisible) {
        document.title = `(${unreadCount}) ${originalTitle}`;
    } else {
        document.title = originalTitle;
    }
}

/**
 * Reset unread count when page becomes visible
 */
function resetUnreadCount() {
    unreadCount = 0;
    updatePageTitle();
}

/**
 * Handle page visibility change
 */
function handleVisibilityChange() {
    isPageVisible = !document.hidden;

    if (isPageVisible) {
        resetUnreadCount();
    }
}

/**
 * Update notification UI based on permission
 */
function updateNotificationUI() {
    const permission = getNotificationPermission();

    if (!notificationsSupported()) {
        notificationToggle.style.display = 'none';
        return;
    }

    switch (permission) {
        case 'granted':
            notificationToggle.classList.add('bg-green-500/20', 'text-green-400');
            notificationToggle.classList.remove('bg-red-500/20', 'text-red-400');
            notificationIcon.textContent = '🔔';
            notificationText.textContent = 'On';
            notificationBanner.classList.add('hidden');
            notificationsEnabled = true;
            break;

        case 'denied':
            notificationToggle.classList.add('bg-red-500/20', 'text-red-400');
            notificationToggle.classList.remove('bg-green-500/20', 'text-green-400');
            notificationIcon.textContent = '🔕';
            notificationText.textContent = 'Blocked';
            notificationBanner.classList.add('hidden');
            notificationsEnabled = false;
            break;

        case 'default':
            notificationToggle.classList.remove('bg-green-500/20', 'text-green-400', 'bg-red-500/20', 'text-red-400');
            notificationIcon.textContent = '🔔';
            notificationText.textContent = 'Off';

            // Show banner if not dismissed
            const dismissed = localStorage.getItem('notification-banner-dismissed');
            if (!dismissed) {
                setTimeout(() => {
                    notificationBanner.classList.remove('hidden');
                }, 3000);  // Show after 3 seconds
            }
            break;
    }
}

/**
 * Save notification preference
 */
function saveNotificationPreference(enabled) {
    localStorage.setItem('notifications-enabled', enabled ? 'true' : 'false');
}

/**
 * Load notification preference
 */
function loadNotificationPreference() {
    const saved = localStorage.getItem('notifications-enabled');
    if (saved === 'true' && getNotificationPermission() === 'granted') {
        notificationsEnabled = true;
    }
}

/**
 * Toggle sound on/off
 */
function toggleSound() {
    soundEnabled = !soundEnabled;
    localStorage.setItem('sound-enabled', soundEnabled ? 'true' : 'false');

    if (soundEnabled) {
        playNotificationSound();  // Test sound
    }
}

/**
 * Load sound preference
 */
function loadSoundPreference() {
    const saved = localStorage.getItem('sound-enabled');
    soundEnabled = saved !== 'false';  // Default to true
}

// ========================================================================
// EVENT LISTENERS FOR NOTIFICATIONS
// ========================================================================

// Notification toggle button
notificationToggle.addEventListener('click', async function () {
    const permission = getNotificationPermission();

    if (permission === 'default') {
        await requestNotificationPermission();
    } else if (permission === 'granted') {
        // Toggle on/off
        notificationsEnabled = !notificationsEnabled;
        saveNotificationPreference(notificationsEnabled);
        updateNotificationUI();

        if (notificationsEnabled) {
            showTestNotification();
        }
    } else if (permission === 'denied') {
        alert('Notifications are blocked. Please enable them in your browser settings.');
    }
});

// Allow notifications button
btnAllow.addEventListener('click', async function () {
    await requestNotificationPermission();
    notificationBanner.classList.add('hidden');
});

// Dismiss notifications banner
btnDismiss.addEventListener('click', function () {
    notificationBanner.classList.add('hidden');
    localStorage.setItem('notification-banner-dismissed', 'true');
});

// Page visibility change
document.addEventListener('visibilitychange', handleVisibilityChange);

// Window focus/blur
window.addEventListener('focus', function () {
    isPageVisible = true;
    resetUnreadCount();
});

window.addEventListener('blur', function () {
    isPageVisible = false;
});

// ========================================================================
// WEBSOCKET AND CHAT FUNCTIONS
// ========================================================================

/**
 * Initialize WebSocket connection
 */
function connectWebSocket() {
    chatSocket = new WebSocket(wsUrl);

    chatSocket.onopen = function (e) {
        console.log('WebSocket connection established');
        updateConnectionStatus(true);
        messageInput.disabled = false;
        sendButton.disabled = false;
    };

    chatSocket.onmessage = function (e) {
        const data = JSON.parse(e.data);

        if (data.type === 'message_history') {
            handleInitialMessages(data);
        }
        else if (data.type === 'load_more_response') {
            handleLoadMoreResponse(data);
        }
        else if (data.type === 'message') {
            displayMessage(data);
            scrollToBottom();

            // NEW: Show notification for received messages
            handleNewMessageNotification(data);
        }
        else if (data.type === 'user_status') {
            updateUserStatus(data.username, data.is_online, data.last_seen);
        }
        else if (data.type === 'typing_indicator') {
            handleTypingIndicator(data.username, data.is_typing);
        }
        else if (data.type === 'read_receipt') {
            handleReadReceipt(data.message_ids, data.read_by);
        }
    };

    chatSocket.onclose = function (e) {
        console.log('WebSocket connection closed');
        updateConnectionStatus(false);
        messageInput.disabled = true;
        sendButton.disabled = true;
        setTimeout(connectWebSocket, 3000);
    };

    chatSocket.onerror = function (error) {
        console.error('WebSocket error:', error);
        updateConnectionStatus(false);
    };
}

// File upload handling
fileInput.addEventListener('change', function (e) {
    const file = e.target.files[0];
    if (file) {
        selectedFile = file;
        previewFilename.textContent = file.name;
        previewFilesize.textContent = formatFileSize(file.size);
        filePreview.classList.remove('hidden');
    }
});

removeFileBtn.addEventListener('click', function () {
    selectedFile = null;
    fileInput.value = '';
    filePreview.classList.add('hidden');
});

async function uploadFile(file, messageText) {
    const formData = new FormData();
    formData.append('file', file);
    if (messageText) {
        formData.append('message', messageText);
    }

    uploadProgress.classList.remove('hidden');
    progressFill.style.width = '0%';
    progressPercent.textContent = '0%';

    try {
        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', function (e) {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                progressFill.style.width = percentComplete + '%';
                progressPercent.textContent = Math.round(percentComplete) + '%';
            }
        });

        xhr.addEventListener('load', function () {
            uploadProgress.classList.add('hidden');

            if (xhr.status === 200) {
                const response = JSON.parse(xhr.responseText);

                if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
                    chatSocket.send(JSON.stringify({
                        'type': 'file_message',
                        'message_id': response.message_id
                    }));
                }

                selectedFile = null;
                fileInput.value = '';
                filePreview.classList.add('hidden');
            } else {
                alert('Upload failed: ' + xhr.statusText);
            }
        });

        xhr.addEventListener('error', function () {
            uploadProgress.classList.add('hidden');
            alert('Upload failed. Please try again.');
        });

        xhr.open('POST', uploadUrl);
        xhr.setRequestHeader('X-CSRFToken', csrfToken);
        xhr.send(formData);

    } catch (error) {
        uploadProgress.classList.add('hidden');
        console.error('Upload error:', error);
        alert('Upload failed. Please try again.');
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function getFileIcon(fileType) {
    if (fileType.startsWith('image/')) return '🖼️';
    if (fileType.includes('pdf')) return '📄';
    if (fileType.includes('word') || fileType.includes('doc')) return '📝';
    if (fileType.includes('zip') || fileType.includes('rar')) return '📦';
    return '📎';
}

function createIntersectionObserver() {
    const options = {
        root: messagesContainer,
        rootMargin: '0px',
        threshold: 0.5
    };

    return new IntersectionObserver((entries) => {
        const visibleUnreadIds = [];

        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const messageId = entry.target.dataset.messageId;
                const sender = entry.target.dataset.sender;

                if (sender === otherUser && unreadMessageIds.has(messageId)) {
                    visibleUnreadIds.push(messageId);
                    unreadMessageIds.delete(messageId);
                }
            }
        });

        if (visibleUnreadIds.length > 0) {
            sendReadReceipt(visibleUnreadIds);
        }
    }, options);
}

function sendReadReceipt(messageIds) {
    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        chatSocket.send(JSON.stringify({
            'type': 'mark_as_read',
            'message_ids': messageIds
        }));
    }
}

function handleReadReceipt(messageIds, readBy) {
    messageIds.forEach(messageId => {
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        if (messageElement) {
            updateReadIndicator(messageElement, true);
        }
    });
}

function updateReadIndicator(messageElement, isRead) {
    const readIndicator = messageElement.querySelector('.read-indicator');
    if (readIndicator) {
        if (isRead) {
            readIndicator.classList.remove('sent');
            readIndicator.classList.add('read');
            readIndicator.innerHTML = createDoubleCheckmark();
        } else {
            readIndicator.classList.add('sent');
            readIndicator.classList.remove('read');
            readIndicator.innerHTML = createSingleCheckmark();
        }
    }
}

function createSingleCheckmark() {
    return `<svg class="w-4 h-4 text-white/70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>`;
}

function createDoubleCheckmark() {
    return `<svg class="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>
                <svg class="w-4 h-4 text-green-400 ml-[-8px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>`;
}

function handleInitialMessages(data) {
    if (initialLoading) initialLoading.style.display = 'none';

    // Clear existing messages
    const indicators = [loadMoreIndicator, typingIndicator, endOfMessages];
    messagesContainer.innerHTML = '';
    indicators.forEach(el => {
        if (el) messagesContainer.appendChild(el);
    });

    currentOffset = data.offset || data.messages.length;
    hasMoreMessages = data.has_more || false;
    totalMessageCount = data.total_count || 0;

    const messages = [...data.messages].reverse();
    messages.forEach(msg => {
        displayMessage(msg, false);
        if (msg.sender === otherUser && !msg.is_read) {
            unreadMessageIds.add(msg.message_id);
        }
    });

    isInitialLoad = false;
    scrollToBottom();

    // Show end of messages if no more to load
    if (!hasMoreMessages && endOfMessages) {
        endOfMessages.classList.remove('hidden');
    }
}

function handleLoadMoreResponse(data) {
    loadMoreIndicator.classList.add('hidden');
    isLoadingMore = false;

    currentOffset = data.offset;
    hasMoreMessages = data.has_more || false;

    if (data.messages && data.messages.length > 0) {
        const previousScrollHeight = messagesContainer.scrollHeight;
        const previousScrollTop = messagesContainer.scrollTop;

        const messages = [...data.messages].reverse();
        messages.forEach(msg => {
            displayMessage(msg, false, true);
            if (msg.sender === otherUser && !msg.is_read) {
                unreadMessageIds.add(msg.message_id);
            }
        });

        const newScrollHeight = messagesContainer.scrollHeight;
        messagesContainer.scrollTop = previousScrollTop + (newScrollHeight - previousScrollHeight);
    }

    // Show end of messages if no more to load
    if (!hasMoreMessages && endOfMessages) {
        endOfMessages.classList.remove('hidden');
    }
}

function handleScroll() {
    if (isLoadingMore || !hasMoreMessages || isInitialLoad) return;
    if (messagesContainer.scrollTop < SCROLL_THRESHOLD) {
        loadMoreMessages();
    }
}

function loadMoreMessages() {
    if (isLoadingMore || !hasMoreMessages) return;
    isLoadingMore = true;
    loadMoreIndicator.classList.remove('hidden');

    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        chatSocket.send(JSON.stringify({
            'type': 'load_more',
            'offset': currentOffset
        }));
    }
}

function sendTypingStatus(isTyping) {
    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        chatSocket.send(JSON.stringify({
            'type': 'typing',
            'is_typing': isTyping
        }));
    }
}

function handleInputTyping() {
    if (!isCurrentlyTyping) {
        isCurrentlyTyping = true;
        sendTypingStatus(true);
    }

    clearTimeout(typingTimer);
    typingTimer = setTimeout(() => {
        isCurrentlyTyping = false;
        sendTypingStatus(false);
    }, TYPING_TIMER_LENGTH);
}

function handleTypingIndicator(username, isTyping) {
    if (username !== otherUser) return;

    if (isTyping) {
        typingIndicator.classList.remove('hidden');
        scrollToBottom();
    } else {
        typingIndicator.classList.add('hidden');
    }
}

function updateUserStatus(username, isOnline, lastSeen) {
    if (username !== otherUser) return;

    if (onlineStatusIndicator) {
        if (isOnline) {
            onlineStatusIndicator.classList.remove('bg-gray-400');
            onlineStatusIndicator.classList.add('bg-green-400', 'animate-pulse');
            lastSeenText.textContent = 'Online';
            lastSeenText.classList.remove('text-white/60');
            lastSeenText.classList.add('text-green-400');
        } else {
            onlineStatusIndicator.classList.remove('bg-green-400', 'animate-pulse');
            onlineStatusIndicator.classList.add('bg-gray-400');
            if (lastSeen) {
                const lastSeenDate = new Date(lastSeen);
                lastSeenText.textContent = `Last seen ${getTimeAgo(lastSeenDate)}`;
                lastSeenText.classList.remove('text-green-400');
                lastSeenText.classList.add('text-white/60');
            }
        }
    }
}

function getTimeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000);
    const intervals = { year: 31536000, month: 2592000, week: 604800, day: 86400, hour: 3600, minute: 60 };

    for (const [unit, secondsInUnit] of Object.entries(intervals)) {
        const interval = Math.floor(seconds / secondsInUnit);
        if (interval >= 1) {
            return `${interval} ${unit}${interval > 1 ? 's' : ''} ago`;
        }
    }
    return 'just now';
}

function displayMessage(data, animate = true, prepend = false) {
    const messageDiv = document.createElement('div');
    const isSent = data.sender === currentUser;
    messageDiv.className = `flex ${isSent ? 'justify-end' : 'justify-start'} animate-fadeIn`;
    messageDiv.dataset.messageId = data.message_id;
    messageDiv.dataset.sender = data.sender;

    if (!animate) messageDiv.style.animation = 'none';

    const timestamp = new Date(data.timestamp);
    const timeString = timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    let messageContent = '';

    if (data.has_file) {
        if (data.is_image) {
            messageContent = `
                    <div class="mb-2">
                        <img src="${data.file_url}" alt="${escapeHtml(data.file_name)}" 
                             class="max-w-full md:max-w-md rounded-2xl cursor-pointer hover:scale-[1.02] transition-transform duration-200"
                             onclick="window.open('${data.file_url}', '_blank')">
                    </div>
                `;
            if (data.message) {
                messageContent += `<div class="mt-2">${escapeHtml(data.message)}</div>`;
            }
        } else {
            const fileIcon = getFileIcon(data.file_type);
            const downloadUrl = `/download/${data.message_id}/`;
            messageContent = `
                    <div class="bg-black/10 backdrop-blur-sm rounded-xl p-3 mb-2">
                        <div class="flex items-center space-x-3">
                            <div class="bg-gradient-to-br from-indigo-500/20 to-purple-500/20 p-2 rounded-lg">
                                <span class="text-lg">${fileIcon}</span>
                            </div>
                            <div class="flex-1 min-w-0">
                                <div class="font-medium text-white truncate">${escapeHtml(data.file_name)}</div>
                                <div class="text-white/60 text-sm">${formatFileSize(data.file_size)}</div>
                            </div>
                            <a href="${downloadUrl}" class="bg-gradient-to-r from-indigo-700 to-purple-700 hover:from-indigo-600 hover:to-purple-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 hover:scale-105" download>
                                Download
                            </a>
                        </div>
                    </div>
                `;
            if (data.message) {
                messageContent = `<div class="mb-2">${escapeHtml(data.message)}</div>` + messageContent;
            }
        }
    } else {
        messageContent = escapeHtml(data.message);
    }

    let readIndicatorHtml = '';
    if (isSent) {
        const isRead = data.is_read || false;
        readIndicatorHtml = `
                <div class="read-indicator flex items-center space-x-1 ${isRead ? 'text-green-400' : 'text-white/70'}">
                    ${isRead ? createDoubleCheckmark() : createSingleCheckmark()}
                </div>
            `;
    }

    messageDiv.innerHTML = `
            <div class="max-w-[85%] md:max-w-2xl ${prepend ? 'order-first' : ''}">
                <div class="${isSent ? 'bg-gradient-to-r from-indigo-700 to-purple-700 text-white rounded-2xl rounded-br-lg' : 'bg-black/10 backdrop-blur-sm text-white/70 rounded-2xl rounded-bl-lg'} p-3 md:p-4 shadow-lg">
                    ${messageContent}
                </div>
                <div class="flex items-center ${isSent ? 'justify-end' : 'justify-start'} mt-1 space-x-2">
                    <span class="text-white/50 text-xs">${timeString}</span>
                    ${readIndicatorHtml}
                </div>
            </div>
        `;

    if (prepend) {
        const insertAfter = endOfMessages || loadMoreIndicator;
        if (insertAfter) {
            messagesContainer.insertBefore(messageDiv, insertAfter.nextSibling);
        } else {
            messagesContainer.prepend(messageDiv);
        }
    } else {
        messagesContainer.insertBefore(messageDiv, typingIndicator);
    }

    if (!isSent && !data.is_read) {
        intersectionObserver.observe(messageDiv);
    }
}

function sendMessage(e) {
    e.preventDefault();

    const message = messageInput.value.trim();

    if (selectedFile) {
        uploadFile(selectedFile, message);
        messageInput.value = '';
    }
    else if (message && chatSocket.readyState === WebSocket.OPEN) {
        chatSocket.send(JSON.stringify({
            'type': 'message',
            'message': message
        }));
        messageInput.value = '';
    }

    messageInput.focus();

    clearTimeout(typingTimer);
    if (isCurrentlyTyping) {
        isCurrentlyTyping = false;
        sendTypingStatus(false);
    }
}

function updateConnectionStatus(isConnected) {
    if (isConnected) {
        connectionStatus.textContent = 'Connected';
        connectionStatus.classList.remove('bg-black/20', 'text-white/90');
        connectionStatus.classList.add('bg-green-500/30', 'text-green-300');
    } else {
        connectionStatus.textContent = 'Disconnected';
        connectionStatus.classList.remove('bg-green-500/30', 'text-green-300');
        connectionStatus.classList.add('bg-red-500/30', 'text-red-300');
    }
}

function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Event listeners
chatForm.addEventListener('submit', sendMessage);
messageInput.addEventListener('input', handleInputTyping);
messageInput.addEventListener('keypress', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(e);
    }
});
messageInput.addEventListener('blur', function () {
    clearTimeout(typingTimer);
    if (isCurrentlyTyping) {
        isCurrentlyTyping = false;
        sendTypingStatus(false);
    }
});

messagesContainer.addEventListener('scroll', handleScroll);

// NEW: Initialize notifications on page load
loadNotificationPreference();
loadSoundPreference();
updateNotificationUI();

// Initialize WebSocket
connectWebSocket();