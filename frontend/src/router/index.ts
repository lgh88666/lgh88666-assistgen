import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Login from '../views/Login.vue'
import EcommerceService from '../views/EcommerceService.vue'

const DEMO_AUTH_ENABLED = true

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: Home,
      meta: { requiresAuth: true }
    },
    {
      path: '/login',
      name: 'login',
      component: Login
    },
    {
      path: '/register',
      name: 'register',
      component: Login
    },
    {
      path: '/ecommerce',
      name: 'ecommerce',
      component: EcommerceService
    }
  ]
})

router.beforeEach((to, _from, next) => {
  if (DEMO_AUTH_ENABLED) {
    localStorage.setItem('token', localStorage.getItem('token') || 'demo-token')
    localStorage.setItem('user_id', localStorage.getItem('user_id') || '1')
    if (to.path === '/login' || to.path === '/register') {
      next('/')
      return
    }
    next()
    return
  }

  const token = localStorage.getItem('token')
  if ((to.path === '/login' || to.path === '/register') && token) {
    next('/')
    return
  }
  if (!token && to.path !== '/login' && to.path !== '/register') {
    next('/login')
    return
  }
  next()
})

export default router
