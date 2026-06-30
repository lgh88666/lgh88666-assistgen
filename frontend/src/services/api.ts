import { ChatMessage } from '../types'
import axios from './axios'
import router from '../router'
import { sha256 } from '../utils/crypto'

// 接口定义
interface StreamChunk {
  type?: 'think' | 'response'
  content: string
}

export interface UserCreate {
  username: string
  email: string
  password: string
}

export interface UserLogin {
  email: string
  password: string
}

export interface Token {
  access_token: string
  token_type: string
}

export interface Conversation {
  id: number
  created_at: string
  title: string
  status: 'ongoing' | 'completed'
  dialogue_type: string
}

export interface Message {
  id: number
  conversation_id: number
  sender: 'user' | 'assistant'
  content: string
  created_at: string
  message_type: string
}

export class ApiService {
  private static baseUrl = import.meta.env.VITE_API_BASE_URL

  // 处理聊天消息流
  static async handleChatStream(reader: ReadableStreamDefaultReader<Uint8Array>, 
                              onChunk: (chunk: StreamChunk) => void) {
    const decoder = new TextDecoder()
    let thinkContent = ''
    let responseContent = ''
    let isInThinkingMode = false
    
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        
        // 解码当前数据块
        const text = decoder.decode(value)
        
        // 处理数据行
        const lines = text.split('\n')
        
        for (const line of lines) {
          // 检查是否是数据行
          if (line.startsWith('data: ')) {
            const content = line.slice(6).trim() // 移除 'data: ' 前缀
            
            // 检查是否是结束标记
            if (content === '[DONE]') continue
            
            // 清理内容 (移除引号和转义)
            const cleanContent = content
              .replace(/^"|"$/g, '') // 移除开头和结尾的引号
              .replace(/\\"/g, '"')  // 处理转义的引号
              .replace(/\\n/g, '\n'); // 处理转义的换行符
            
            // 检查是否包含思考过程标记
            if (content.includes('<think>')) {
              isInThinkingMode = true
              const thinkMatch = content.match(/<think>([\s\S]*?)<\/think>/);
              
              if (thinkMatch && thinkMatch[1]) {
                // 如果找到完整标签，提取内容
                thinkContent = thinkMatch[1].trim()
                  .replace(/^"|"$/g, '') // 额外清理引号
                  .replace(/\\"/g, '"');
                onChunk({ type: 'think', content: thinkContent })
                isInThinkingMode = false
              } else {
                // 提取部分内容
                const startContent = content.split('<think>')[1];
                if (startContent) {
                  thinkContent = startContent.trim()
                    .replace(/^"|"$/g, '') // 额外清理引号
                    .replace(/\\"/g, '"');
                  onChunk({ type: 'think', content: thinkContent })
                }
              }
            } else if (content.includes('</think>')) {
              // 处理结束标签
              isInThinkingMode = false
              
              // 提取结束标签前的内容
              const endContent = content.split('</think>')[0];
              if (endContent) {
                thinkContent += endContent.trim()
                  .replace(/^"|"$/g, '') // 额外清理引号
                  .replace(/\\"/g, '"');
                onChunk({ type: 'think', content: thinkContent })
              }
              
              // 检查标签后的内容
              const afterThink = content.split('</think>')[1];
              if (afterThink && afterThink.trim()) {
                responseContent += afterThink.trim()
                  .replace(/^"|"$/g, '') // 额外清理引号
                  .replace(/\\"/g, '"');
                onChunk({ type: 'response', content: responseContent })
              }
            } else if (isInThinkingMode) {
              // 思考模式中的内容
              thinkContent += cleanContent;
              onChunk({ type: 'think', content: thinkContent })
            } else {
              // 普通响应
              responseContent += cleanContent;
              onChunk({ type: 'response', content: responseContent })
            }
          }
        }
      }
    } catch (error) {
      console.error('Error reading stream:', error)
      throw error
    }
  }

  // 创建新会话
  static async createConversation(): Promise<number> {
    const response = await fetch(`${this.baseUrl}/api/conversations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify({
        user_id: localStorage.getItem('user_id')
      })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const data = await response.json()
    return data.conversation_id
  }

  // 聊天接口
  static async chat(messages: ChatMessage[], conversationId: number) {
    if (!conversationId) {
      throw new Error('Missing conversation_id')
    }

    const response = await fetch(`${this.baseUrl}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify({
        messages,
        user_id: localStorage.getItem('user_id'),
        conversation_id: conversationId
      })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    return response.body?.getReader()
  }

  // 推理接口
  static async reason(messages: ChatMessage[], conversationId: number) {
    if (!conversationId) {
      throw new Error('Missing conversation_id')
    }

    const response = await fetch(`${this.baseUrl}/api/reason`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify({
        messages,
        user_id: localStorage.getItem('user_id'),
        conversation_id: conversationId
      })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    return response.body?.getReader()
  }

  // 搜索接口
  static async search(messages: ChatMessage[], conversationId: number) {
    if (!conversationId) {
      throw new Error('Missing conversation_id')
    }

    const response = await fetch(`${this.baseUrl}/api/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify({
        messages,
        user_id: localStorage.getItem('user_id'),
        conversation_id: conversationId
      })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    return response.body?.getReader()
  }

  // 获取用户的所有会话
  static async getUserConversations(userId: string): Promise<Conversation[]> {
    const response = await fetch(`${this.baseUrl}/api/conversations/user/${userId}`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    return response.json()
  }

  // 获取特定会话的所有消息
  static async getConversationMessages(conversationId: number): Promise<Message[]> {
    const userId = localStorage.getItem('user_id')
    const response = await fetch(`${this.baseUrl}/api/conversations/${conversationId}/messages?user_id=${userId}`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    return response.json()
  }

  // 删除会话
  static async deleteConversation(conversationId: number): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/conversations/${conversationId}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
  }

  // 更新会话名称
  static async updateConversationName(conversationId: number, name: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/conversations/${conversationId}/name`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify({ name })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
  }
}

export const AuthService = {
  async register(data: UserCreate): Promise<Token> {
    const hashedPassword = await sha256(data.password)
    const response = await axios.post('/api/register', {
      username: data.username,
      email: data.email,
      password: hashedPassword
    })
    return response.data
  },

  async login(data: UserLogin): Promise<Token> {
    const hashedPassword = await sha256(data.password)
    const response = await axios.post('/api/token', {
      email: data.email,
      password: hashedPassword
    }, {
      headers: {
        'Content-Type': 'application/json'
      }
    })
    return response.data
  },

  async logout() {
    localStorage.removeItem('token')
    router.push('/login')
  },

  async validateToken() {
    try {
      await axios.get('/api/validate-token')
      return true
    } catch {
      return false
    }
  },

  async getUserInfo() {
    const response = await axios.get('/api/users/me')
    return response.data
  }
}