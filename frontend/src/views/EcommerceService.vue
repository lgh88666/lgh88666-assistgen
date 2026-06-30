<template>
  <div class="ecommerce-container">
    <!-- 头部导航栏 -->
    <header class="header">
      <div class="top-bar">
        <div class="top-container">
          <div class="location">中国大陆版 · 北京</div>
          <div class="login-info">
            <span>您好，</span>
            <a href="#" class="login">请登录</a>
            <a href="#" class="register">免费注册</a>
          </div>
          <div class="top-nav">
            <a href="#" @click="backToMain">AI助手</a>
            <a href="#">我的订单</a>
            <a href="#">我的购物车 <span class="badge">1</span></a>
            <a href="#">商家服务</a>
            <a href="#">网站导航</a>
          </div>
        </div>
      </div>
      <div class="header-main-container">
        <div class="main-header">
          <div class="logo" @click="backToMain">
            <div class="logo-box">赋范</div>
          </div>
          <div class="search-box">
            <input type="text" placeholder="小白熊恒温调奶器" v-model="searchInput"/>
            <button class="search-btn">搜索</button>
          </div>
          <div class="cart">
            <div class="cart-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M9 22C9.55228 22 10 21.5523 10 21C10 20.4477 9.55228 20 9 20C8.44772 20 8 20.4477 8 21C8 21.5523 8.44772 22 9 22Z" stroke="black" stroke-width="2"/>
                <path d="M20 22C20.5523 22 21 21.5523 21 21C21 20.4477 20.5523 20 20 20C19.4477 20 19 20.4477 19 21C19 21.5523 19.4477 22 20 22Z" stroke="black" stroke-width="2"/>
                <path d="M1 1H5L7.68 14.39C7.77144 14.8504 8.02191 15.264 8.38755 15.5583C8.75318 15.8526 9.2107 16.009 9.68 16H19.4C19.8693 16.009 20.3268 15.8526 20.6925 15.5583C21.0581 15.264 21.3086 14.8504 21.4 14.39L23 6H6" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <span class="cart-count">1</span>
            </div>
            <span>购物车</span>
          </div>
        </div>
      </div>
      <div class="nav-wrapper">
        <div class="nav-container">
          <div class="nav-menu">
            <div class="categories">
              <span>全部商品分类</span>
            </div>
            <ul class="menu-items">
              <li><a href="#">首页</a></li>
              <li><a href="#">热销商品</a></li>
              <li><a href="#">新品上市</a></li>
              <li><a href="#">优惠活动</a></li>
              <li><a href="#">品牌专区</a></li>
              <li><a href="#">客服中心</a></li>
            </ul>
          </div>
        </div>
      </div>
      <div class="quick-links">
        <div class="quick-links-container">
          <ul class="links-list">
            <li><a href="#">出口转内销又好又便宜</a></li>
            <li><a href="#">得力办公约100件好物</a></li>
            <li><a href="#">户外鞋服馆</a></li>
            <li><a href="#">风扇空调</a></li>
            <li><a href="#">冲锋衣</a></li>
            <li><a href="#">黄金项链</a></li>
            <li><a href="#">小狗KP</a></li>
            <li><a href="#">跑步机</a></li>
            <li><a href="#">智能手表</a></li>
          </ul>
        </div>
      </div>
    </header>

    <!-- 主要内容区域 -->
    <div class="main-content">
      <!-- 左侧分类导航 -->
      <div class="sidebar">
        <ul class="category-list">
          <li><i class="icon">📱</i> 手机/运营商/数码</li>
          <li><i class="icon">💻</i> 电脑/办公</li>
          <li><i class="icon">🏠</i> 家居/家具/家装/厨具</li>
          <li><i class="icon">👕</i> 男装/女装/童装/内衣</li>
          <li><i class="icon">👟</i> 美妆/个护清洁/宠物</li>
          <li><i class="icon">💍</i> 女鞋/箱包/钟表/珠宝</li>
          <li><i class="icon">🏃</i> 男鞋/运动/户外</li>
          <li><i class="icon">🚗</i> 汽车/汽车用品</li>
          <li><i class="icon">👶</i> 母婴/玩具乐器</li>
          <li><i class="icon">🍚</i> 食品/酒类/生鲜/特产</li>
        </ul>
      </div>

      <!-- 右侧内容区域 -->
      <div class="content">
        <!-- Banner区域 -->
        <div class="banner-area" style="display: none;">
          <div class="main-banner">
            <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI3MDAiIGhlaWdodD0iMzAwIj48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImdyYWQiIHgxPSIwJSIgeTE9IjAlIiB4Mj0iMTAwJSIgeTI9IjEwMCUiPjxzdG9wIG9mZnNldD0iMCUiIHN0b3AtY29sb3I9IiNmZmVlZWUiLz48c3RvcCBvZmZzZXQ9IjEwMCUiIHN0b3AtY29sb3I9IiNkZGVmYmIiLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48cmVjdCB3aWR0aD0iNzAwIiBoZWlnaHQ9IjMwMCIgZmlsbD0idXJsKCNncmFkKSIvPjx0ZXh0IHg9IjM1MCIgeT0iMTUwIiBmb250LXNpemU9IjMwIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjNjY2Ij7lpJrku7flk4jotKjkuK3lv4M8L3RleHQ+PC9zdmc+" alt="Banner" />
          </div>
        </div>
        
        <!-- 小banner区域 -->
        <div class="side-banners-container" style="display: none;">
          <div class="side-banner">
            <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMjAiIGhlaWdodD0iMTQ1Ij48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImdyYWQiIHgxPSIwJSIgeTE9IjAlIiB4Mj0iMTAwJSIgeTI9IjEwMCUiPjxzdG9wIG9mZnNldD0iMCUiIHN0b3AtY29sb3I9IiNlMGVhZmMiLz48c3RvcCBvZmZzZXQ9IjEwMCUiIHN0b3AtY29sb3I9IiNjZmRlZjMiLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48cmVjdCB3aWR0aD0iMjIwIiBoZWlnaHQ9IjE0NSIgZmlsbD0idXJsKCNncmFkKSIvPjx0ZXh0IHg9IjExMCIgeT0iNzAiIGZvbnQtc2l6ZT0iMTgiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiM2NjYiPuWNleWTgeS8mOWMljwvdGV4dD48L3N2Zz4=" alt="Side Banner 1" />
          </div>
          <div class="side-banner">
            <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMjAiIGhlaWdodD0iMTQ1Ij48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImdyYWQiIHgxPSIwJSIgeTE9IjAlIiB4Mj0iMTAwJSIgeTI9IjEwMCUiPjxzdG9wIG9mZnNldD0iMCUiIHN0b3AtY29sb3I9IiNmZmQxZDEiLz48c3RvcCBvZmZzZXQ9IjEwMCUiIHN0b3AtY29sb3I9IiNmZmE4YTgiLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48cmVjdCB3aWR0aD0iMjIwIiBoZWlnaHQ9IjE0NSIgZmlsbD0idXJsKCNncmFkKSIvPjx0ZXh0IHg9IjExMCIgeT0iNzAiIGZvbnQtc2l6ZT0iMTgiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiM2NjYiPuS6keWNleS8mOaDoOa0vjwvdGV4dD48L3N2Zz4=" alt="Side Banner 2" />
          </div>
        </div>

        <!-- 推荐商品区域 -->
        <div class="recommended-products">
          <div class="section-header">
            <h2>为您推荐</h2>
            <a href="#" class="more-link">更多好货 ></a>
          </div>
          <div class="product-list">
            <div class="product-card" v-for="(product, index) in recommendedProducts" :key="index">
              <div class="product-image" :data-name="product.name">
                <img :src="product.image" :alt="product.name" />
              </div>
              <div class="product-info">
                <h3 class="product-name">{{ product.name }}</h3>
                <p class="product-desc">{{ product.description }}</p>
                <div class="product-price">¥{{ product.price }}</div>
                <button class="add-to-cart-btn">加入购物车</button>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 热销商品区域 -->
        <div class="hot-products">
          <div class="section-header">
            <h2>热销商品</h2>
            <a href="#" class="more-link">更多热卖 ></a>
          </div>
          <div class="product-list">
            <div class="product-card" v-for="(product, index) in hotProducts" :key="index">
              <div class="product-image" :data-name="product.name">
                <img :src="product.image" :alt="product.name" />
              </div>
              <div class="product-info">
                <h3 class="product-name">{{ product.name }}</h3>
                <p class="product-desc">{{ product.description }}</p>
                <div class="product-price">¥{{ product.price }}</div>
                <button class="add-to-cart-btn">加入购物车</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 客服浮动按钮 -->
    <div class="chat-float-btn" @click="toggleChatPopup">
      <div class="chat-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
          <path d="M21 11.5C21.0034 12.8199 20.6951 14.1219 20.1 15.3C19.3944 16.7118 18.3098 17.8992 16.9674 18.7293C15.6251 19.5594 14.0782 19.9994 12.5 20C11.1801 20.0035 9.87812 19.6951 8.7 19.1L3 21L4.9 15.3C4.30493 14.1219 3.99656 12.8199 4 11.5C4.00061 9.92179 4.44061 8.37488 5.27072 7.03258C6.10083 5.69028 7.28825 4.6056 8.7 3.90003C9.87812 3.30496 11.1801 2.99659 12.5 3.00003H13C15.0843 3.11502 17.053 3.99479 18.5291 5.47089C20.0052 6.94699 20.885 8.91568 21 11V11.5Z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <span>联系客服</span>
    </div>

    <!-- 聊天弹窗 -->
    <div class="chat-popup" v-if="showChatPopup">
      <div class="chat-popup-header">
        <h3>在线客服</h3>
        <button class="close-btn" @click="showChatPopup = false">×</button>
      </div>
      <div class="chat-popup-messages" ref="messagesContainer">
        <div v-for="(message, index) in messages" 
             :key="index"
             :class="['popup-message', message.role === 'user' ? 'popup-user-message' : 'popup-assistant-message']">
          <!-- 如果有图片，显示图片 -->
          <div v-if="message.imageUrl" class="message-image">
            <img :src="message.imageUrl" alt="用户上传图片" />
          </div>
          <!-- 显示文本内容 -->
          <div class="popup-message-content" v-html="renderMessage(message.content)"></div>
        </div>
      </div>
      <div class="chat-popup-input">
        <input 
          type="text" 
          v-model="userInput" 
          @keyup.enter="sendMessage"
          placeholder="请输入您想咨询的问题..."
        />
        <label class="upload-btn">
          <input type="file" accept="image/*" @change="handleImageUpload" ref="fileInput" style="display:none" />
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M4 16L8.586 11.414C8.96106 11.0391 9.46967 10.8284 10 10.8284C10.5303 10.8284 11.0389 11.0391 11.414 11.414L16 16M14 14L15.586 12.414C15.9611 12.0391 16.4697 11.8284 17 11.8284C17.5303 11.8284 18.0389 12.0391 18.414 12.414L20 14M14 8H14.01M6 20H18C18.5304 20 19.0391 19.7893 19.4142 19.4142C19.7893 19.0391 20 18.5304 20 18V6C20 5.46957 19.7893 4.96086 19.4142 4.58579C19.0391 4.21071 18.5304 4 18 4H6C5.46957 4 4.96086 4.21071 4.58579 4.58579C4.21071 4.96086 4 5.46957 4 6V18C4 18.5304 4.21071 19.0391 4.58579 19.4142C4.96086 19.7893 5.46957 20 6 20Z" stroke="#666" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </label>
        <button class="send-btn" @click="sendMessage">发送</button>
      </div>
    </div>

    <!-- 底部区域 -->
    <footer class="footer">
      <div class="footer-links">
        <div class="link-group">
          <h3>购物指南</h3>
          <ul>
            <li><a href="#">购物流程</a></li>
            <li><a href="#">会员介绍</a></li>
            <li><a href="#">生活旅行</a></li>
            <li><a href="#">常见问题</a></li>
          </ul>
        </div>
        <div class="link-group">
          <h3>配送方式</h3>
          <ul>
            <li><a href="#">上门自提</a></li>
            <li><a href="#">211限时达</a></li>
            <li><a href="#">配送服务查询</a></li>
            <li><a href="#">配送费收取标准</a></li>
          </ul>
        </div>
        <div class="link-group">
          <h3>支付方式</h3>
          <ul>
            <li><a href="#">货到付款</a></li>
            <li><a href="#">在线支付</a></li>
            <li><a href="#">分期付款</a></li>
            <li><a href="#">公司转账</a></li>
          </ul>
        </div>
        <div class="link-group">
          <h3>售后服务</h3>
          <ul>
            <li><a href="#">售后政策</a></li>
            <li><a href="#">价格保护</a></li>
            <li><a href="#">退款说明</a></li>
            <li><a href="#">返修/退换货</a></li>
          </ul>
        </div>
      </div>
      <div class="copyright">
        Copyright © 2023 AI电商客服. All Rights Reserved.
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import MarkdownIt from 'markdown-it'
import axios from 'axios'

const router = useRouter()
const md = new MarkdownIt()
const messagesContainer = ref<HTMLElement | null>(null)
const userInput = ref('')
const searchInput = ref('')
const showChatPopup = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const isUploading = ref(false)
const conversationId = ref<string | null>(null)

// 消息列表
const messages = ref<{ role: 'user' | 'assistant', content: string, isLoading?: boolean, imageUrl?: string }[]>([
  {
    role: 'assistant',
    content: '您好！我是智能客服助手，有什么可以帮您的吗？ 😊'
  }
])

// 推荐商品
const recommendedProducts = ref([
  {
    name: 'Anker 20000mAh 移动电源',
    description: '大容量快充，双向充电，适用于iPhone、iPad、安卓设备',
    price: 159.00,
    image: 'data:image/svg+xml;charset=utf8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22 viewBox=%220 0 200 200%22%3E%3Crect width=%22200%22 height=%22200%22 fill=%22%23f0f0f0%22/%3E%3Cpath d=%22M50 70h100v60H50z%22 fill=%22%23FF4D4F%22 opacity=%220.8%22/%3E%3Cpath d=%22M60 80h80v40H60z%22 fill=%22%23FFF%22/%3E%3Ccircle cx=%2270%22 cy=%22100%22 r=%225%22 fill=%22%23FF4D4F%22/%3E%3Ccircle cx=%2285%22 cy=%22100%22 r=%225%22 fill=%22%23FF4D4F%22/%3E%3C/svg%3E'
  },
  {
    name: '小米 11 Ultra 5G手机',
    description: '骁龙888处理器，120Hz高刷新率，67W快充',
    price: 5499.00,
    image: 'data:image/svg+xml;charset=utf8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22 viewBox=%220 0 200 200%22%3E%3Crect width=%22200%22 height=%22200%22 fill=%22%23f0f0f0%22/%3E%3Crect x=%2270%22 y=%2250%22 width=%2260%22 height=%22100%22 rx=%225%22 fill=%22%23FF4D4F%22 opacity=%220.7%22/%3E%3Crect x=%2275%22 y=%2255%22 width=%2250%22 height=%2280%22 rx=%222%22 fill=%22white%22/%3E%3Ccircle cx=%22100%22 cy=%22145%22 r=%225%22 fill=%22%23555%22/%3E%3C/svg%3E'
  },
  {
    name: 'Apple AirPods Pro',
    description: '主动降噪，空间音频，入耳检测，IPX4防水',
    price: 1999.00,
    image: 'data:image/svg+xml;charset=utf8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22 viewBox=%220 0 200 200%22%3E%3Crect width=%22200%22 height=%22200%22 fill=%22%23f0f0f0%22/%3E%3Cpath d=%22M70 60C70 60 80 70 80 90C80 100 77 105 75 110C73 115 70 120 60 120C50 120 47 115 45 110C43 105 40 100 40 90C40 70 50 60 50 60%22 fill=%22white%22 stroke=%22%23555%22 stroke-width=%223%22/%3E%3Cpath d=%22M150 60C150 60 140 70 140 90C140 100 143 105 145 110C147 115 150 120 160 120C170 120 173 115 175 110C177 105 180 100 180 90C180 70 170 60 170 60%22 fill=%22white%22 stroke=%22%23555%22 stroke-width=%223%22/%3E%3Cpath d=%22M110 130L90 120%22 stroke=%22%23555%22 stroke-width=%223%22/%3E%3Cpath d=%22M110 130L130 120%22 stroke=%22%23555%22 stroke-width=%223%22/%3E%3Ccircle cx=%22110%22 cy=%22130%22 r=%2210%22 fill=%22%23555%22/%3E%3C/svg%3E'
  },
  {
    name: '华为 MateBook 14',
    description: '11代酷睿i7，16GB内存，512GB固态硬盘',
    price: 6299.00,
    image: 'data:image/svg+xml;charset=utf8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22 viewBox=%220 0 200 200%22%3E%3Crect width=%22200%22 height=%22200%22 fill=%22%23f0f0f0%22/%3E%3Cpath d=%22M40 70h120v60H40z%22 fill=%22%23333%22/%3E%3Cpath d=%22M40 130h120v10H40z%22 fill=%22%23555%22/%3E%3Ccircle cx=%22100%22 cy=%22135%22 r=%222%22 fill=%22%23fff%22/%3E%3C/svg%3E'
  }
])

// 热销商品
const hotProducts = ref([
  {
    name: '小米智能手环6',
    description: '1.56英寸AMOLED大屏，血氧监测，14天超长续航',
    price: 249.00,
    image: 'data:image/svg+xml;charset=utf8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22 viewBox=%220 0 200 200%22%3E%3Crect width=%22200%22 height=%22200%22 fill=%22%23f0f0f0%22/%3E%3Crect x=%2280%22 y=%2260%22 width=%2240%22 height=%2280%22 rx=%2220%22 fill=%22%23FF4D4F%22 opacity=%220.8%22/%3E%3Crect x=%2285%22 y=%2265%22 width=%2230%22 height=%2270%22 rx=%225%22 fill=%22white%22/%3E%3C/svg%3E'
  },
  {
    name: '荣耀50 Pro',
    description: '骁龙778G，100W超级快充，1亿像素超清影像',
    price: 2999.00,
    image: 'data:image/svg+xml;charset=utf8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22 viewBox=%220 0 200 200%22%3E%3Crect width=%22200%22 height=%22200%22 fill=%22%23f0f0f0%22/%3E%3Crect x=%2265%22 y=%2245%22 width=%2270%22 height=%22110%22 rx=%228%22 fill=%22%23FF8800%22 opacity=%220.8%22/%3E%3Crect x=%2270%22 y=%2250%22 width=%2260%22 height=%2290%22 rx=%224%22 fill=%22white%22/%3E%3Ccircle cx=%22100%22 cy=%22150%22 r=%224%22 fill=%22%23333%22/%3E%3Ccircle cx=%2285%22 cy=%2260%22 r=%223%22 fill=%22%23333%22/%3E%3Ccircle cx=%22100%22 cy=%2260%22 r=%223%22 fill=%22%23333%22/%3E%3Ccircle cx=%22115%22 cy=%2260%22 r=%223%22 fill=%22%23333%22/%3E%3C/svg%3E'
  },
  {
    name: 'OPPO Reno6',
    description: '天玑900，65W超级闪充，AI人像视频',
    price: 2799.00,
    image: 'data:image/svg+xml;charset=utf8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22 viewBox=%220 0 200 200%22%3E%3Crect width=%22200%22 height=%22200%22 fill=%22%23f0f0f0%22/%3E%3Crect x=%2265%22 y=%2250%22 width=%2270%22 height=%22110%22 rx=%226%22 fill=%22%2300A0E9%22 opacity=%220.8%22/%3E%3Crect x=%2270%22 y=%2255%22 width=%2260%22 height=%2290%22 rx=%224%22 fill=%22white%22/%3E%3Ccircle cx=%22100%22 cy=%22150%22 r=%224%22 fill=%22%2300A0E9%22/%3E%3Ccircle cx=%2285%22 cy=%2265%22 r=%224%22 fill=%22%2300A0E9%22/%3E%3Ccircle cx=%22100%22 cy=%2265%22 r=%224%22 fill=%22%2300A0E9%22/%3E%3C/svg%3E'
  },
  {
    name: '罗技 MX Master 3鼠标',
    description: '高精度传感器，定制按键，多设备控制',
    price: 699.00,
    image: 'data:image/svg+xml;charset=utf8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22 viewBox=%220 0 200 200%22%3E%3Crect width=%22200%22 height=%22200%22 fill=%22%23f0f0f0%22/%3E%3Cpath d=%22M60 80C60 60 80 60 100 60C120 60 140 60 140 80C140 100 140 120 100 120C60 120 60 100 60 80Z%22 fill=%22%23444%22/%3E%3Cpath d=%22M95 60C95 60 100 50 105 60%22 stroke=%22%23444%22 stroke-width=%222%22/%3E%3Ccircle cx=%22100%22 cy=%2270%22 r=%222%22 fill=%22%23ccc%22/%3E%3Cpath d=%22M100 75L100 90%22 stroke=%22%23ccc%22 stroke-width=%221%22/%3E%3C/svg%3E'
  }
])

// 返回主页
const backToMain = () => {
  router.push('/')
}

// 切换聊天弹窗显示
const toggleChatPopup = () => {
  showChatPopup.value = !showChatPopup.value
  
  if (showChatPopup.value) {
    // 如果是新打开的聊天窗口，重置会话ID
    if (conversationId.value === null) {
      conversationId.value = 'ecommerce_' + Date.now().toString();
    }
    
    nextTick(() => {
      scrollToBottom()
    })
  }
}

// 发送消息
const sendMessage = async () => {
  if (!userInput.value.trim()) return
  
  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: userInput.value
  })
  
  const userQuestion = userInput.value
  userInput.value = ''
  
  // 滚动到底部
  await nextTick()
  scrollToBottom()
  
  try {
    // 获取用户ID
    const userId = localStorage.getItem('user_id')
    if (!userId) {
      throw new Error('用户ID不存在')
    }
    
    // 显示加载状态
    messages.value.push({
      role: 'assistant',
      content: '正在思考...',
      isLoading: true
    })
    
    // 创建FormData
    const formData = new FormData()
    formData.append('query', userQuestion)
    formData.append('user_id', userId)
    
    // 添加会话ID
    if (conversationId.value) {
      formData.append('conversation_id', conversationId.value)
    }
    
    // 调用API
    const response = await fetch('http://localhost:8000/api/langgraph/query', {
      method: 'POST',
      body: formData
    })
    
    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`)
    }
    
    // 存储返回的会话ID（如果有）
    const returnedConversationId = response.headers.get('X-Conversation-ID')
    if (returnedConversationId) {
      conversationId.value = returnedConversationId
    }
    
    // 移除加载消息
    const loadingMsgIndex = messages.value.findIndex(msg => msg.isLoading)
    if (loadingMsgIndex !== -1) {
      messages.value.splice(loadingMsgIndex, 1)
    }
    
    // 检查响应类型
    const contentType = response.headers.get('Content-Type')
    
    // 如果是流式响应
    if (contentType && contentType.includes('text/event-stream')) {
      // 添加一个空的助手消息
      messages.value.push({
        role: 'assistant',
        content: ''
      })
      
      // 获取reader
      const reader = response.body?.getReader()
      if (!reader) throw new Error('无法读取响应流')
      
      // 处理流
      await handleChatStream(reader)
    } else {
      // 非流式响应，处理JSON
      const result = await response.json()
      messages.value.push({
        role: 'assistant',
        content: result.response || '抱歉，我无法处理您的请求。'
      })
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    
    // 移除加载消息
    const loadingMsgIndex = messages.value.findIndex(msg => msg.isLoading)
    if (loadingMsgIndex !== -1) {
      messages.value.splice(loadingMsgIndex, 1)
    }
    
    // 添加错误提示
    messages.value.push({
      role: 'assistant',
      content: '抱歉，发生了错误，请稍后再试。'
    })
  }
}

// 处理聊天流
const handleChatStream = async (reader: ReadableStreamDefaultReader<Uint8Array>) => {
  const decoder = new TextDecoder()
  let currentContent = ''
  
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
  
      const chunk = decoder.decode(value)
      const lines = chunk.split('\n')
      
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        
        const content = line.slice(6) // 移除 'data: ' 前缀
        if (content === '[DONE]') continue
        
        // 处理所有可能的换行符形式
        if (content === '"\\n\\n"' || content === '"\n\n"' || content === '\n\n') {
          currentContent += '\n\n'
          continue
        }
        
        // 移除引号
        let cleanedContent = content
        if (cleanedContent.startsWith('"') && cleanedContent.endsWith('"')) {
          cleanedContent = cleanedContent.slice(1, -1)
        }
        
        // 处理转义的换行符
        cleanedContent = cleanedContent.replace(/\\n\\n/g, '\n\n').replace(/\\n/g, '\n')
  
        // 添加到当前内容
        currentContent += cleanedContent
        
        // 更新最后一条消息的内容
        const lastMessage = messages.value[messages.value.length - 1]
        lastMessage.content = currentContent
        
        // 滚动到底部
        await nextTick()
        scrollToBottom()
      }
    }
  } catch (error) {
    console.error('Error handling chat stream:', error)
    const lastMessage = messages.value[messages.value.length - 1]
    lastMessage.content = '抱歉，发生了错误，请稍后重试。'
  }
}

// 渲染消息内容
const renderMessage = (content: string) => {
  // 使用无空行的Markdown配置
  const customMd = new MarkdownIt({
    breaks: true,
    html: false,
    linkify: true,
  })
  
  // 处理段落标签，去掉额外空白
  const html = customMd.render(content)
  return html.replace(/<p>(.*?)<\/p>/g, '$1').replace(/<br><br>/g, '<br>')
}

// 滚动到底部
const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// 处理图片上传
const handleImageUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement
  if (!target || !target.files || target.files.length === 0) return

  const file = target.files[0]
  if (!file) return

  try {
    // 获取用户ID
    const userId = localStorage.getItem('user_id')
    if (!userId) {
      throw new Error('用户ID不存在')
    }

    // 显示上传中状态
    isUploading.value = true

    // 添加图片消息到聊天
    messages.value.push({
      role: 'user',
      content: '[上传图片中...]',
      isLoading: true
    })

    // 直接发送图片到langgraph API
    const formData = new FormData()
    formData.append('query', '用户上传了图片，需要调用视觉模型进行分析')
    formData.append('user_id', userId)
    formData.append('image', file)
    
    // 添加会话ID
    if (conversationId.value) {
      formData.append('conversation_id', conversationId.value)
    }

    // 调用API
    const response = await fetch('http://localhost:8000/api/langgraph/query', {
      method: 'POST',
      body: formData
    })

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`)
    }
    
    // 存储返回的会话ID（如果有）
    const returnedConversationId = response.headers.get('X-Conversation-ID')
    if (returnedConversationId) {
      conversationId.value = returnedConversationId
    }
    
    // 更新消息状态
    const loadingMsgIndex = messages.value.findIndex(msg => msg.isLoading)
    if (loadingMsgIndex !== -1) {
      messages.value[loadingMsgIndex] = {
        role: 'user',
        content: '',
        imageUrl: URL.createObjectURL(file)
      }
    }

    // 清空文件输入
    if (fileInput.value) {
      fileInput.value.value = ''
    }

    // 检查响应类型
    const contentType = response.headers.get('Content-Type')
    
    // 如果是流式响应
    if (contentType && contentType.includes('text/event-stream')) {
      // 添加一个空的助手消息
      messages.value.push({
        role: 'assistant',
        content: ''
      })
      
      // 获取reader
      const reader = response.body?.getReader()
      if (!reader) throw new Error('无法读取响应流')
      
      // 处理流
      await handleChatStream(reader)
    } else {
      // 非流式响应，处理JSON
      const result = await response.json()
      messages.value.push({
        role: 'assistant',
        content: result.response || '抱歉，我无法分析这张图片。'
      })
    }

  } catch (error) {
    console.error('图片上传失败:', error)
    
    // 更新或移除加载消息
    const loadingMsgIndex = messages.value.findIndex(msg => msg.isLoading)
    if (loadingMsgIndex !== -1) {
      messages.value.splice(loadingMsgIndex, 1)
    }
    
    // 显示错误消息
    messages.value.push({
      role: 'assistant',
      content: '抱歉，图片上传或分析失败，请稍后重试。'
    })
  } finally {
    isUploading.value = false
  }
}

onMounted(() => {
  scrollToBottom()
})
</script>

<style scoped>
.ecommerce-container {
  width: 100%;
  min-height: 100vh;
  background-color: #f5f5f5;
  font-family: Arial, sans-serif;
  color: #333;
}

/* 头部样式 */
.header {
  width: 100%;
  background-color: #fff;
}

.top-bar {
  height: 30px;
  background-color: #e3e4e5;
  display: flex;
  align-items: center;
  padding: 0;
  color: #999;
  font-size: 12px;
}

.top-container {
  display: flex;
  align-items: center;
  width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
}

.location {
  margin-right: 20px;
}

.login-info {
  margin-right: auto;
}

.login-info a {
  color: #ff4d4f;
  margin: 0 5px;
  text-decoration: none;
}

.top-nav {
  display: flex;
}

.top-nav a {
  color: #999;
  margin-left: 15px;
  text-decoration: none;
}

.top-nav a:hover {
  color: #ff4d4f;
}

.badge {
  background-color: #ff4d4f;
  color: white;
  border-radius: 50%;
  font-size: 10px;
  padding: 1px 4px;
}

.header-main-container {
  padding: 0;
  border-bottom: 1px solid #eee;
}

.main-header {
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
}

.logo {
  margin-right: 40px;
  cursor: pointer;
}

.logo-box {
  width: 120px;
  height: 40px;
  background-color: #ff4d4f;
  color: white;
  font-size: 24px;
  font-weight: bold;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.search-box {
  flex: 1;
  max-width: 600px;
  height: 36px;
  display: flex;
  margin-right: 40px;
}

.search-box input {
  flex: 1;
  height: 100%;
  padding: 0 15px;
  border: 2px solid #ff4d4f;
  border-right: none;
  border-top-left-radius: 20px;
  border-bottom-left-radius: 20px;
  font-size: 14px;
  outline: none;
}

.search-btn {
  width: 80px;
  height: 100%;
  background-color: #ff4d4f;
  color: white;
  border: none;
  border-top-right-radius: 20px;
  border-bottom-right-radius: 20px;
  font-size: 16px;
  cursor: pointer;
}

.cart {
  display: flex;
  align-items: center;
  color: #333;
  font-size: 14px;
}

.cart-icon {
  position: relative;
  margin-right: 8px;
}

.cart-icon svg path {
  stroke: #333;
}

.cart-count {
  position: absolute;
  top: -5px;
  right: -5px;
  background-color: #ff4d4f;
  color: white;
  font-size: 10px;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.nav-wrapper {
  background-color: #ff4d4f;
  width: 100%;
}

.nav-container {
  width: 1200px;
  margin: 0 auto;
}

.nav-menu {
  display: flex;
  height: 40px;
}

.categories {
  width: 180px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #d23c3e;
  color: white;
  font-weight: bold;
  font-size: 14px;
  cursor: pointer;
}

.menu-items {
  flex: 1;
  display: flex;
  list-style: none;
  margin: 0;
  padding: 0;
}

.menu-items li {
  margin: 0;
  line-height: 40px;
  padding: 0 15px;
}

.menu-items a {
  color: white;
  text-decoration: none;
  font-size: 14px;
  font-weight: normal;
}

.menu-items a:hover {
  color: #fff;
  opacity: 0.8;
}

/* 主内容区域样式 */
.main-content {
  display: flex;
  padding: 0;
  width: 1200px;
  margin: 0 auto;
}

.sidebar {
  width: 200px;
  background-color: #fff;
  border-radius: 4px;
  overflow: hidden;
  margin-right: 10px;
}

.category-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.category-list li {
  padding: 10px 15px;
  border-bottom: 1px solid #eee;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
}

.category-list li:hover {
  background-color: #f5f5f5;
  color: #ff4d4f;
}

.icon {
  margin-right: 10px;
}

.content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.banner-area {
  display: none;
  width: 100%;
  margin-bottom: 20px;
}

.main-banner {
  width: 100%;
  height: 300px;
  background: linear-gradient(135deg, #ffeeee 0%, #ddefbb 100%);
  border-radius: 8px;
  overflow: hidden;
}

.main-banner img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.side-banners-container {
  display: none;
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
}

.side-banner {
  flex: 1;
  height: 145px;
  background: linear-gradient(135deg, #e0eafc 0%, #cfdef3 100%);
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.side-banner:hover {
  transform: translateY(-3px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.side-banner img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 推荐商品区域样式 */
.recommended-products {
  background-color: #fff;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.section-header h2 {
  font-size: 18px;
  color: #333;
  margin: 0;
}

.more-link {
  color: #999;
  text-decoration: none;
  font-size: 14px;
}

.product-list {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.product-card {
  border-radius: 8px;
  overflow: hidden;
  background-color: #fff;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.product-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.product-image {
  position: relative;
  height: 200px;
  overflow: hidden;
  border-radius: 8px 8px 0 0;
  background: linear-gradient(135deg, #f8f8f8 0%, #e0e0e0 100%);
  display: flex;
  justify-content: center;
  align-items: center;
}

.product-image::before {
  content: attr(data-name);
  position: absolute;
  font-size: 16px;
  font-weight: bold;
  color: #666;
  text-align: center;
  padding: 0 10px;
  z-index: 1;
  display: none; /* 隐藏重叠的文字 */
}

.product-image img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  transition: all 0.3s ease;
  z-index: 2;
}

.product-image img:not([src]), 
.product-image img[src=""], 
.product-image img[src="error"],
.product-image img[src$="undefined"] {
  opacity: 0;
}

.product-card:hover .product-image img {
  transform: scale(1.05);
}

.product-info {
  padding: 15px;
}

.product-name {
  font-size: 16px;
  font-weight: 500;
  margin: 0 0 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.product-desc {
  font-size: 12px;
  color: #666;
  margin: 0 0 10px;
  height: 36px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.product-price {
  font-size: 18px;
  font-weight: bold;
  color: #ff4d4f;
  margin-bottom: 10px;
}

.add-to-cart-btn {
  width: 100%;
  height: 36px;
  background-color: #ff4d4f;
  color: #fff;
  border: none;
  border-radius: 18px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.add-to-cart-btn:hover {
  background-color: #ff7875;
}

/* 热销商品区域样式 */
.hot-products {
  background-color: #fff;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.section-header h2 {
  font-size: 18px;
  color: #333;
  margin: 0;
}

.more-link {
  color: #999;
  text-decoration: none;
  font-size: 14px;
}

.product-list {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.product-card {
  border-radius: 8px;
  overflow: hidden;
  background-color: #fff;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.product-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.product-image {
  position: relative;
  height: 200px;
  overflow: hidden;
  border-radius: 8px 8px 0 0;
  background: linear-gradient(135deg, #f8f8f8 0%, #e0e0e0 100%);
  display: flex;
  justify-content: center;
  align-items: center;
}

.product-image::before {
  content: attr(data-name);
  position: absolute;
  font-size: 16px;
  font-weight: bold;
  color: #666;
  text-align: center;
  padding: 0 10px;
  z-index: 1;
  display: none; /* 隐藏重叠的文字 */
}

.product-image img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  transition: all 0.3s ease;
  z-index: 2;
}

.product-image img:not([src]), 
.product-image img[src=""], 
.product-image img[src="error"],
.product-image img[src$="undefined"] {
  opacity: 0;
}

.product-card:hover .product-image img {
  transform: scale(1.05);
}

.product-info {
  padding: 15px;
}

.product-name {
  font-size: 16px;
  font-weight: 500;
  margin: 0 0 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.product-desc {
  font-size: 12px;
  color: #666;
  margin: 0 0 10px;
  height: 36px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.product-price {
  font-size: 18px;
  font-weight: bold;
  color: #ff4d4f;
  margin-bottom: 10px;
}

.add-to-cart-btn {
  width: 100%;
  height: 36px;
  background-color: #ff4d4f;
  color: #fff;
  border: none;
  border-radius: 18px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.add-to-cart-btn:hover {
  background-color: #ff7875;
}

/* 客服浮动按钮样式 */
.chat-float-btn {
  position: fixed;
  bottom: 30px;
  right: 30px;
  background-color: #ff4d4f;
  color: white;
  border-radius: 50px;
  padding: 15px 20px;
  display: flex;
  align-items: center;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(255, 77, 79, 0.4);
  z-index: 999;
  transition: all 0.3s;
}

.chat-float-btn:hover {
  transform: translateY(-3px);
  box-shadow: 0 6px 16px rgba(255, 77, 79, 0.5);
}

.chat-icon {
  width: 24px;
  height: 24px;
}

.chat-float-btn span {
  margin-left: 10px;
  font-size: 14px;
  font-weight: bold;
}

/* 聊天弹窗样式 */
.chat-popup {
  position: fixed;
  bottom: 30px;
  right: 30px;
  width: 360px;
  height: 500px;
  background-color: white;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  z-index: 1000;
  overflow: hidden;
}

.chat-popup-header {
  background-color: #ff4d4f;
  padding: 15px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chat-popup-header h3 {
  margin: 0;
  font-size: 16px;
  color: white;
  font-weight: 500;
}

.close-btn {
  background: none;
  color: white;
  border: none;
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
}

.chat-popup-messages {
  flex: 1;
  overflow-y: auto;
  padding: 15px;
  background-color: #f8f8f8;
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.popup-message {
  max-width: 80%;
  padding: 12px 16px;
  border-radius: 16px;
  position: relative;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

.popup-user-message {
  align-self: flex-end;
  background-color: #ff4d4f;
  color: white;
  border-bottom-right-radius: 4px;
}

.popup-assistant-message {
  align-self: flex-start;
  background-color: white;
  color: #333;
  border-bottom-left-radius: 4px;
}

.popup-message-content {
  white-space: pre-wrap;
  line-height: 1.5;
  font-size: 14px;
}

.popup-message-content :deep(p) {
  margin: 0;
}

/* 消息中的图片样式 */
.message-image {
  margin-bottom: 8px;
  max-width: 100%;
}

.message-image img {
  max-width: 100%;
  max-height: 200px;
  border-radius: 8px;
  object-fit: contain;
}

.chat-popup-input {
  display: flex;
  gap: 8px;
  padding: 12px;
  background-color: white;
  border-top: 1px solid #eee;
}

.chat-popup-input input {
  flex: 1;
  height: 40px;
  padding: 0 15px;
  border: 1px solid #ddd;
  border-radius: 20px;
  outline: none;
  font-size: 14px;
}

.chat-popup-input input:focus {
  border-color: #ff4d4f;
}

.chat-popup-input .upload-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: none;
  background: #f5f5f5;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.3s;
}

.chat-popup-input .upload-btn:hover {
  background: #e0e0e0;
}

.chat-popup-input .upload-btn svg {
  width: 20px;
  height: 20px;
}

.chat-popup-input .send-btn {
  width: 70px;
  height: 40px;
  background-color: #ff4d4f;
  color: white;
  border: none;
  border-radius: 20px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

/* 底部区域样式 */
.footer {
  background-color: #fff;
  padding: 30px 20px;
  margin-top: 30px;
}

.footer-links {
  display: flex;
  justify-content: space-around;
  padding: 30px 0;
  max-width: 1200px;
  margin: 0 auto;
}

.link-group h3 {
  font-size: 16px;
  color: #333;
  margin-bottom: 15px;
}

.link-group ul {
  list-style: none;
  padding: 0;
}

.link-group li {
  margin-bottom: 10px;
}

.link-group a {
  color: #666;
  text-decoration: none;
  font-size: 12px;
}

.link-group a:hover {
  color: #ff4d4f;
}

.copyright {
  text-align: center;
  color: #999;
  font-size: 12px;
  padding-top: 20px;
  border-top: 1px solid #eee;
  max-width: 1200px;
  margin: 0 auto;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .main-content {
    flex-direction: column;
  }
  
  .sidebar {
    width: 100%;
    margin-right: 0;
    margin-bottom: 20px;
  }
  
  .product-list {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .footer-links {
    flex-wrap: wrap;
  }
  
  .link-group {
    width: 50%;
    margin-bottom: 20px;
  }
}

.product-section {
  margin-top: 30px;
  max-width: 1200px;
  margin-left: auto;
  margin-right: auto;
}

.products {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-top: 20px;
}

.service-section {
  margin-top: 40px;
  padding: 20px;
  background-color: #f9f9f9;
  border-radius: 10px;
  max-width: 1200px;
  margin-left: auto;
  margin-right: auto;
}

.quick-links {
  width: 100%;
  background-color: #fff;
  border-bottom: 1px solid #eee;
  margin-bottom: 10px;
}

.quick-links-container {
  width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
}

.links-list {
  list-style: none;
  padding: 8px 0;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
}

.links-list li {
  margin-right: 15px;
  font-size: 12px;
  line-height: 22px;
}

.links-list a {
  color: #666;
  text-decoration: none;
}

.links-list a:hover {
  color: #ff4d4f;
}
</style> 