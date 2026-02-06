class TrainBookingApp {
    constructor() {
        this.currentTrain = null;
        this.selectedPassengers = [];
        this.seatType = 'O';
        this.qrUuid = null;
        this.loginModal = null;
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.checkLoginStatus();
        this.setMinDate();
        this.loadStations();
    }
    
    bindEvents() {
        // 登录相关事件
        document.getElementById('loginBtn').addEventListener('click', () => {
            this.showLoginModal();
        });
        
        // 车票查询事件
        document.getElementById('ticketForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.queryTickets();
        });
        
        // 乘客选择事件 - 使用事件委托
        document.getElementById('passengerList').addEventListener('click', (e) => {
            // 查找被点击的乘客项
            let target = e.target;
            // 如果点击的是图标或文本，向上查找包含data-id的父元素
            while (target && !target.hasAttribute('data-id')) {
                target = target.parentElement;
            }
            
            if (target && target.classList.contains('passenger-item')) {
                this.togglePassengerSelection(target);
            }
        });
        
        // 座位类型选择事件
        document.getElementById('seatType').addEventListener('change', (e) => {
            this.seatType = e.target.value;
        });
        
        // 提交订单事件
        document.getElementById('bookBtn').addEventListener('click', () => {
            this.submitBooking();
        });
    }
    
    setMinDate() {
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('travelDate').min = today;
        document.getElementById('travelDate').value = today;
    }
    
    async checkLoginStatus() {
        try {
            const response = await fetch('/api/user/status');
            const data = await response.json();
            
            if (data.success && data.logged_in) {
                this.updateLoginStatus(true);
                this.loadPassengers();
            } else {
                this.updateLoginStatus(false);
            }
        } catch (error) {
            console.error('检查登录状态失败:', error);
            this.updateLoginStatus(false);
        }
    }
    
    updateLoginStatus(isLoggedIn) {
        const loginStatusText = document.getElementById('loginStatusText');
        const loginBtn = document.getElementById('loginBtn');
        
        if (isLoggedIn) {
            loginStatusText.innerHTML = '<i class="fas fa-user-check me-1"></i>已登录';
            loginStatusText.classList.add('loggedIn');
            loginBtn.innerHTML = '<i class="fas fa-sync-alt me-1"></i>重新登录';
            loginBtn.className = 'btn btn-outline-light btn-sm';
        } else {
            loginStatusText.innerHTML = '<i class="fas fa-user me-1"></i>未登录';
            loginStatusText.classList.remove('loggedIn');
            loginBtn.innerHTML = '<i class="fas fa-qrcode me-1"></i>扫码登录';
            loginBtn.className = 'btn btn-outline-light btn-sm';
        }
    }
    
    async showLoginModal() {
        if (!this.loginModal) {
            this.loginModal = new bootstrap.Modal(document.getElementById('loginModal'));
        }
        
        // 显示模态框
        this.loginModal.show();
        
        // 生成二维码
        await this.generateQRCode();
    }
    
    async generateQRCode() {
        const qrCodeDiv = document.getElementById('qrCode');
        const statusText = document.getElementById('loginModalStatusText');
        
        try {
            qrCodeDiv.style.display = 'none';
            statusText.innerHTML = '<div class="login-status-text text-info"><i class="fas fa-spinner fa-spin me-2"></i>正在生成二维码...</div>';
            
            const response = await fetch('/api/login/qrcode', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.qrUuid = data.uuid;
                
                // 显示二维码
                qrCodeDiv.innerHTML = `<img src="data:image/png;base64,${data.qr_image}" alt="登录二维码">`;
                qrCodeDiv.style.display = 'block';
                statusText.innerHTML = '<div class="login-status-text text-info"><i class="fas fa-info-circle me-2"></i>请使用12306手机APP扫描二维码</div>';
                
                // 开始轮询登录状态
                this.pollLoginStatus();
            } else {
                qrCodeDiv.style.display = 'none';
                statusText.innerHTML = `<div class="login-status-text text-danger"><i class="fas fa-exclamation-triangle me-2"></i>生成二维码失败: ${data.message}</div>`;
            }
        } catch (error) {
            console.error('生成二维码失败:', error);
            qrCodeDiv.style.display = 'none';
            statusText.innerHTML = '<div class="login-status-text text-danger"><i class="fas fa-exclamation-triangle me-2"></i>网络错误，请稍后重试</div>';
        }
    }
    
    async pollLoginStatus() {
        const statusText = document.getElementById('loginModalStatusText');
        
        const checkStatus = async () => {
            try {
                const response = await fetch(`/api/login/status/${this.qrUuid}`);
                const data = await response.json();
                
                if (data.success) {
                    switch (data.status) {
                        case 'waiting':
                            statusText.innerHTML = '<div class="login-status-text text-info"><i class="fas fa-clock me-2"></i>等待扫描...</div>';
                            break;
                        case 'scanned':
                            statusText.innerHTML = '<div class="login-status-text text-warning"><i class="fas fa-mobile-alt me-2"></i>已扫描，请在手机上点击确认...</div>';
                            break;
                        case 'success':
                            statusText.innerHTML = '<div class="login-status-text text-success"><i class="fas fa-check-circle me-2"></i>登录成功</div>';
                            
                            // 登录成功，关闭模态框
                            setTimeout(() => {
                                this.loginModal.hide();
                                this.updateLoginStatus(true);
                                this.loadPassengers();
                            }, 1000);
                            return;
                        case 'failed':
                        case 'expired':
                            statusText.innerHTML = `<div class="login-status-text text-danger"><i class="fas fa-times-circle me-2"></i>${data.message}</div>`;
                            return;
                    }
                    
                    // 继续轮询
                    setTimeout(checkStatus, 2000);
                }
            } catch (error) {
                console.error('检查登录状态失败:', error);
                setTimeout(checkStatus, 2000);
            }
        };
        
        // 开始轮询
        checkStatus();
    }
    
    async loadStations() {
        try {
            const response = await fetch('/api/stations');
            const data = await response.json();
            
            if (data.success) {
                // 这里可以用来做自动补全功能
                console.log('车站列表加载成功，共', data.stations.length, '个车站');
            }
        } catch (error) {
            console.error('加载车站列表失败:', error);
        }
    }
    
    async queryTickets() {
        const fromStation = document.getElementById('fromStation').value.trim();
        const toStation = document.getElementById('toStation').value.trim();
        const travelDate = document.getElementById('travelDate').value;
        
        if (!fromStation || !toStation || !travelDate) {
            this.showMessage('请填写完整的查询信息', 'warning');
            return;
        }
        
        // 检查是否已登录
        const loginResponse = await fetch('/api/user/status');
        const loginData = await loginResponse.json();
        
        if (!loginData.success || !loginData.logged_in) {
            this.showMessage('请先登录', 'warning');
            this.showLoginModal();
            return;
        }
        
        // 显示加载状态
        const queryBtn = document.getElementById('queryBtn');
        const originalText = queryBtn.innerHTML;
        queryBtn.innerHTML = '<span class="loading"></span> 查询中...';
        queryBtn.disabled = true;
        
        try {
            const response = await fetch('/api/tickets/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    from_station: fromStation,
                    to_station: toStation,
                    date: travelDate
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.displayTickets(data.trains);
                this.showMessage('查询成功', 'success');
            } else {
                this.showMessage(`查询失败: ${data.message}`, 'danger');
            }
        } catch (error) {
            console.error('查询车票失败:', error);
            this.showMessage('网络错误，请稍后重试', 'danger');
        } finally {
            queryBtn.innerHTML = originalText;
            queryBtn.disabled = false;
        }
    }
    
    displayTickets(trains) {
        const ticketTableBody = document.getElementById('ticketTableBody');
        const ticketResultCard = document.getElementById('ticketResultCard');
        
        if (!trains || trains.length === 0) {
            ticketTableBody.innerHTML = '<tr><td colspan="8" class="text-center">暂无车票信息</td></tr>';
            ticketResultCard.style.display = 'block';
            return;
        }
        
        let html = '';
        trains.forEach((train, index) => {
            html += `
                <tr>
                    <td>${train.train_no}</td>
                    <td>${train.start_time || '--'}</td>
                    <td>${train.arrive_time || '--'}</td>
                    <td>${train.duration || '--'}</td>
                    <td>${train.ze_num || '--'}</td>
                    <td>${train.zy_num || '--'}</td>
                    <td>${train.swz_num || '--'}</td>
                    <td>
                        <button class="btn btn-sm btn-primary select-train-btn" 
                                data-train="${train.train_no}">
                            选择
                        </button>
                    </td>
                </tr>
            `;
        });
        
        ticketTableBody.innerHTML = html;
        ticketResultCard.style.display = 'block';
        
        // 绑定选择车次事件
        document.querySelectorAll('.select-train-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const trainNo = e.target.getAttribute('data-train');
                this.selectTrain(trainNo);
            });
        });
    }
    
    selectTrain(trainNo) {
        this.currentTrain = trainNo;
        this.showMessage(`已选择车次: ${trainNo}`, 'success');
        
        // 显示乘客和座位选择区域
        document.getElementById('passengerCard').style.display = 'block';
        document.getElementById('seatCard').style.display = 'block';
        document.getElementById('bookBtn').style.display = 'block';
        
        // 滚动到选择区域
        document.getElementById('passengerCard').scrollIntoView({ behavior: 'smooth' });
    }
    
    async loadPassengers() {
        try {
            const response = await fetch('/api/passengers');
            const data = await response.json();
            
            if (data.success) {
                this.displayPassengers(data.passengers);
            } else {
                this.showMessage(`加载乘客失败: ${data.message}`, 'danger');
            }
        } catch (error) {
            console.error('加载乘客失败:', error);
            this.showMessage('网络错误，加载乘客失败', 'danger');
        }
    }
    
    displayPassengers(passengers) {
        const passengerList = document.getElementById('passengerList');
        
        if (!passengers || passengers.length === 0) {
            passengerList.innerHTML = '<p class="text-muted">暂无乘客信息</p>';
            return;
        }
        
        let html = '';
        passengers.forEach(passenger => {
            html += `
                <div class="passenger-item" data-id="${passenger.id}">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${passenger.name}</strong>
                            <small class="d-block text-muted">${passenger.id_type}: ${passenger.id_no}</small>
                        </div>
                        <i class="fas fa-check d-none"></i>
                    </div>
                </div>
            `;
        });
        
        passengerList.innerHTML = html;
    }
    
    togglePassengerSelection(element) {
        const passengerId = parseInt(element.getAttribute('data-id'));
        const icon = element.querySelector('i');
        
        console.log('点击了乘客项:', element);
        console.log('乘客ID:', passengerId);
        console.log('当前选中状态:', element.classList.contains('selected'));
        
        if (element.classList.contains('selected')) {
            // 取消选择
            element.classList.remove('selected');
            if (icon) icon.classList.add('d-none');
            this.selectedPassengers = this.selectedPassengers.filter(id => id !== passengerId);
            console.log('取消选择乘客:', passengerId);
        } else {
            // 选择乘客
            element.classList.add('selected');
            if (icon) icon.classList.remove('d-none');
            this.selectedPassengers.push(passengerId);
            console.log('选择乘客:', passengerId);
        }
        
        console.log('当前选择的乘客IDs:', this.selectedPassengers);
    }
    
    async submitBooking() {
        if (!this.currentTrain) {
            this.showMessage('请先选择车次', 'warning');
            return;
        }
        
        if (this.selectedPassengers.length === 0) {
            this.showMessage('请选择乘客', 'warning');
            return;
        }
        
        const fromStation = document.getElementById('fromStation').value.trim();
        const toStation = document.getElementById('toStation').value.trim();
        const travelDate = document.getElementById('travelDate').value;
        
        const bookBtn = document.getElementById('bookBtn');
        const originalText = bookBtn.innerHTML;
        bookBtn.innerHTML = '<span class="loading"></span> 提交中...';
        bookBtn.disabled = true;
        
        try {
            const response = await fetch('/api/booking/submit', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    from_station: fromStation,
                    to_station: toStation,
                    date: travelDate,
                    train_no: this.currentTrain,
                    passenger_ids: this.selectedPassengers,
                    seat_type: this.seatType
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showMessage(data.message, 'success');
                this.displayOrderStatus(data.message, 'success');
            } else {
                this.showMessage(`下单失败: ${data.message}`, 'danger');
                this.displayOrderStatus(data.message, 'danger');
            }
        } catch (error) {
            console.error('提交订单失败:', error);
            this.showMessage('网络错误，提交订单失败', 'danger');
            this.displayOrderStatus('网络错误，提交订单失败', 'danger');
        } finally {
            bookBtn.innerHTML = originalText;
            bookBtn.disabled = false;
        }
    }
    
    displayOrderStatus(message, type) {
        const orderStatusCard = document.getElementById('orderStatusCard');
        const orderStatusText = document.getElementById('orderStatusText');
        
        orderStatusText.innerHTML = `
            <div class="alert alert-${type}">
                <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i>
                ${message}
            </div>
        `;
        orderStatusCard.style.display = 'block';
        
        // 滚动到状态显示区域
        orderStatusCard.scrollIntoView({ behavior: 'smooth' });
    }
    
    showMessage(message, type = 'info') {
        // 创建消息元素
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alertDiv);
        
        // 3秒后自动移除
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.parentNode.removeChild(alertDiv);
            }
        }, 3000);
    }
}

// 页面加载完成后初始化应用
document.addEventListener('DOMContentLoaded', () => {
    new TrainBookingApp();
});
