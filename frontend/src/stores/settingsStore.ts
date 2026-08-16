// 应用设置状态：主题（浅色/深色）与语言（中文/English），持久化到 localStorage
import { create } from 'zustand'
import { translations, type Locale } from '../i18n/translations'

export type Theme = 'light' | 'dark'

const THEME_KEY = 'agent_theme'
const LOCALE_KEY = 'agent_locale'

function loadTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    // 存储不可用时默认浅色
    return 'light'
  }
}

function loadLocale(): Locale {
  try {
    return localStorage.getItem(LOCALE_KEY) === 'en' ? 'en' : 'zh'
  } catch {
    return 'zh'
  }
}

const initialTheme = loadTheme()
// 模块加载时即应用主题，避免页面闪烁（先于 React 渲染）
document.documentElement.setAttribute('data-theme', initialTheme)

interface SettingsState {
  theme: Theme
  locale: Locale
  setTheme: (theme: Theme) => void
  setLocale: (locale: Locale) => void
}

export const useSettingsStore = create<SettingsState>((set) => ({
  theme: initialTheme,
  locale: loadLocale(),
  setTheme: (theme) => {
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      // 忽略存储失败，主题仍即时生效
    }
    document.documentElement.setAttribute('data-theme', theme)
    set({ theme })
  },
  setLocale: (locale) => {
    try {
      localStorage.setItem(LOCALE_KEY, locale)
    } catch {
      // 忽略存储失败，语言仍即时生效
    }
    set({ locale })
  },
}))

// 轻量翻译钩子：返回当前语言字典
export function useTranslation() {
  const locale = useSettingsStore((s) => s.locale)
  return { locale, t: translations[locale] }
}
