import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ApiService, type Conversation, type Message } from '../services/api'

export const useConversationStore = defineStore('conversation', () => {
  const currentConversationId = ref<number | null>(null)
  const isNewConversation = ref(true)
  const conversations = ref<Conversation[]>([])
  const currentMessages = ref<Message[]>([])

  // 创建新会话
  const createNewConversation = async () => {
    try {
      currentConversationId.value = await ApiService.createConversation()
      isNewConversation.value = false
      // 刷新会话列表
      await loadUserConversations()
      return currentConversationId.value
    } catch (error) {
      console.error('Failed to create conversation:', error)
      throw error
    }
  }

  // 加载用户的所有会话
  const loadUserConversations = async () => {
    try {
      const userId = localStorage.getItem('user_id')
      if (!userId) throw new Error('No user ID found')
      conversations.value = await ApiService.getUserConversations(userId)
    } catch (error) {
      console.error('Failed to load conversations:', error)
      throw error
    }
  }

  // 加载特定会话的消息
  const loadConversationMessages = async (conversationId: number) => {
    try {
      currentConversationId.value = conversationId
      isNewConversation.value = false
      currentMessages.value = await ApiService.getConversationMessages(conversationId)
    } catch (error) {
      console.error('Failed to load messages:', error)
      throw error
    }
  }

  // 重置会话状态
  const resetConversation = () => {
    currentConversationId.value = null
    isNewConversation.value = true
    currentMessages.value = []
  }

  // 删除会话
  const deleteConversation = async (conversationId: number) => {
    try {
      await ApiService.deleteConversation(conversationId)
      // 如果删除的是当前会话，重置状态
      if (currentConversationId.value === conversationId) {
        resetConversation()
      }
      // 刷新会话列表
      await loadUserConversations()
    } catch (error) {
      console.error('Failed to delete conversation:', error)
      throw error
    }
  }

  // 更新会话名称
  const updateConversationName = async (conversationId: number, name: string) => {
    try {
      await ApiService.updateConversationName(conversationId, name)
      // 刷新会话列表
      await loadUserConversations()
    } catch (error) {
      console.error('Failed to update conversation name:', error)
      throw error
    }
  }

  return {
    currentConversationId,
    isNewConversation,
    conversations,
    currentMessages,
    createNewConversation,
    loadUserConversations,
    loadConversationMessages,
    resetConversation,
    deleteConversation,
    updateConversationName
  }
}) 