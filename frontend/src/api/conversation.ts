import request from './index';

// 获取所有会话列表
export function getAllConversations() {
  return request.get('/api/conversations');
}

// 创建新会话
export function createConversation() {
  return request.post('/api/conversations');
}

// 添加删除会话的API
export function deleteConversation(conversationId: number) {
  return request.delete(`/api/conversations/${conversationId}`);
}

// 添加修改会话名称的API
export function updateConversationName(conversationId: number, name: string) {
  return request.put(`/api/conversations/${conversationId}/name`, { name });
} 