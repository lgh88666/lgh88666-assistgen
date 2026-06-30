<template>
  <div class="sidebar">
    <div class="sidebar-header">
      <h3>DeepSeek Chat</h3>
      <button class="new-chat-btn" @click="createNewChat">新建会话</button>
    </div>
    <div class="sidebar-content">
      <ul class="conversation-list">
        <li
          v-for="conversation in conversations"
          :key="conversation.id"
          :class="{ active: conversation.id === currentConversationId }"
          @click="switchConversation(conversation.id)"
        >
          <div class="conversation-item">
            <div class="conversation-name">
              <span v-if="!isEditing || editingId !== conversation.id">
                {{ conversation.name || '新会话' }}
              </span>
              <input
                v-else
                v-model="editingName"
                @blur="saveConversationName"
                @keyup.enter="saveConversationName"
                ref="editInput"
                class="edit-input"
              />
            </div>
            
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue';
import { getAllConversations, createConversation, deleteConversation, updateConversationName } from '../api/conversation';
import { useRouter } from 'vue-router';

const router = useRouter();
const conversations = ref<any[]>([]);
const currentConversationId = ref<number | null>(null);

// 编辑会话名称相关状态
const isEditing = ref(false);
const editingId = ref<number | null>(null);
const editingName = ref('');
const editInput = ref<HTMLInputElement | null>(null);

onMounted(async () => {
  await fetchConversations();
});

const fetchConversations = async () => {
  try {
    const response = await getAllConversations();
    conversations.value = response.data;
  } catch (error) {
    console.error('获取会话列表失败', error);
  }
};

const createNewChat = async () => {
  try {
    const response = await createConversation();
    const newConversation = response.data;
    conversations.value.unshift(newConversation);
    switchConversation(newConversation.id);
  } catch (error) {
    console.error('创建新会话失败', error);
  }
};

const switchConversation = (conversationId: number) => {
  currentConversationId.value = conversationId;
  router.push(`/chat/${conversationId}`);
};

// 删除会话
const confirmDeleteConversation = (conversationId: number) => {
  if (confirm('确定要删除这个会话吗？')) {
    deleteCurrentConversation(conversationId);
  }
};

const deleteCurrentConversation = async (conversationId: number) => {
  try {
    await deleteConversation(conversationId);
    conversations.value = conversations.value.filter(c => c.id !== conversationId);
    
    // 如果删除的是当前会话，则切换到第一个会话或创建新会话
    if (currentConversationId.value === conversationId) {
      if (conversations.value.length > 0) {
        switchConversation(conversations.value[0].id);
      } else {
        createNewChat();
      }
    }
  } catch (error) {
    console.error('删除会话失败', error);
  }
};

// 开始编辑会话名称
const startEditName = (conversationId: number, name: string) => {
  isEditing.value = true;
  editingId.value = conversationId;
  editingName.value = name || '新会话';
  
  // 等待DOM更新后聚焦输入框
  nextTick(() => {
    if (editInput.value) {
      editInput.value.focus();
    }
  });
};

// 保存会话名称
const saveConversationName = async () => {
  if (editingId.value && editingName.value.trim()) {
    try {
      await updateConversationName(editingId.value, editingName.value.trim());
      
      // 更新本地会话列表
      const conversation = conversations.value.find(c => c.id === editingId.value);
      if (conversation) {
        conversation.name = editingName.value.trim();
      }
    } catch (error) {
      console.error('更新会话名称失败', error);
    }
  }
  
  // 无论成功失败，都退出编辑模式
  isEditing.value = false;
  editingId.value = null;
  editingName.value = '';
};
</script>

<style scoped>
.sidebar {
  width: 250px;
  height: 100%;
  background-color: #f5f5f5;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #ddd;
}

.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid #ddd;
}

.new-chat-btn {
  width: 100%;
  padding: 8px;
  margin-top: 10px;
  background-color: #4caf50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.new-chat-btn:hover {
  background-color: #45a049;
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
}

.conversation-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.conversation-list li {
  padding: 10px 20px;
  cursor: pointer;
  border-bottom: 1px solid #eee;
  position: relative;
}

.conversation-list li:hover {
  background-color: #e9e9e9;
}

.conversation-list li.active {
  background-color: #e0e0e0;
}

.conversation-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.conversation-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-right: 10px;
}

/* 操作按钮区域 */
.conversation-actions {
  display: none;
  align-items: center;
}

.conversation-item:hover .conversation-actions {
  display: flex;
}

.action-btn {
  background: none;
  border: none;
  width: 24px;
  height: 24px;
  padding: 0;
  margin-left: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  opacity: 0.7;
}

.action-btn:hover {
  opacity: 1;
  background-color: rgba(0,0,0,0.05);
}

.rename-btn {
  color: #555;
}

.delete-btn {
  color: #e53935;
}

.edit-input {
  width: 100%;
  padding: 4px;
  border: 1px solid #ccc;
  border-radius: 3px;
}
</style> 