// Hàm để lấy dữ liệu truyện từ API
async function fetchStories() {
    try {
        const response = await fetch('/api/stories');
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error fetching stories:', error);
        return [];
    }
}

// Hàm tạo card cho mỗi truyện
function createStoryCard(story) {
    const card = document.createElement('div');
    card.className = 'story-card';
    
    // Tạo ảnh bìa ngẫu nhiên cho truyện
    const coverUrl = `https://picsum.photos/300/400?random=${story.id}`;
    
    card.innerHTML = `
        <img src="${coverUrl}" alt="${story.title}">
        <div class="story-info">
            <h3 class="story-title">${story.title}</h3>
            <div class="story-meta">
                <span class="story-chapters">${story.total_chapters} chương</span>
                <span class="story-date">${new Date(story.created_at).toLocaleDateString()}</span>
            </div>
        </div>
    `;
    
    // Thêm sự kiện click để chuyển đến trang đọc truyện
    card.addEventListener('click', () => {
        window.location.href = `/story/${story.id}`;
    });
    
    return card;
}

// Hàm hiển thị truyện lên trang web
async function displayStories() {
    const newestContainer = document.getElementById('newest-stories');
    const completedContainer = document.getElementById('completed-stories');
    
    // Hiển thị loading
    newestContainer.innerHTML = '<div class="loading"></div>';
    completedContainer.innerHTML = '<div class="loading"></div>';
    
    // Lấy dữ liệu truyện
    const stories = await fetchStories();
    
    // Xóa loading
    newestContainer.innerHTML = '';
    completedContainer.innerHTML = '';
    
    // Phân loại truyện
    const newestStories = stories.sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 6);
    const completedStories = stories.filter(story => story.is_completed);
    
    // Hiển thị truyện mới nhất
    newestStories.forEach(story => {
        newestContainer.appendChild(createStoryCard(story));
    });
    
    // Hiển thị truyện đã hoàn thành
    completedStories.forEach(story => {
        completedContainer.appendChild(createStoryCard(story));
    });
}

// Khởi chạy khi trang web được tải
document.addEventListener('DOMContentLoaded', displayStories); 