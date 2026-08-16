// 前端国际化文案字典：zh（中文）/ en（英文）
// 新增文案时在此维护两个语言，组件中通过 useTranslation 取用
export type Locale = 'zh' | 'en'

const zh = {
  sidebar: {
    newChat: '+ 新对话',
    pinned: '置顶',
    today: '今天',
    within7: '7天内',
    within30: '30天内',
    older: '30天以上',
    untitled: '未命名对话',
    rename: '重命名',
    pin: '置顶',
    unpin: '取消置顶',
    delete: '删除',
    logout: '登出',
    settings: '系统设置',
    help: '帮助',
    expand: '展开侧边栏',
    collapse: '收起侧边栏',
    sessionActions: '会话操作',
    userMenu: '用户菜单',
  },
  welcome: {
    intro1: '你好，我是超级个人综合型助手，能通过工具调用帮你完成各类任务。',
    intro2: '你可以询问我“你有什么功能”，我会告诉你我提供的所有功能。',
    features: {
      search: { title: '联网搜索', desc: '实时搜索最新信息与新闻' },
      media: { title: '图片/视频生成', desc: '一句话生成图片与视频' },
      map: { title: '地图服务', desc: '地理编码、天气、路径与周边' },
      code: { title: '编程与竞赛', desc: 'LeetCode 题目、题解' },
    },
  },
  chat: {
    inputPlaceholder: '畅所欲言',
    send: '发送',
    copy: '复制',
    copied: '已复制',
    thinking: '正在思考…',
  },
  tool: {
    call: '调用',
    running: '执行中',
    success: '完成',
    failed: '失败',
  },
  settings: {
    title: '系统设置',
    helpTitle: '帮助',
    theme: '主题',
    light: '浅色',
    dark: '深色',
    language: '语言',
    chinese: '中文',
    english: 'English',
    close: '关闭',
  },
  help: {
    featuresTitle: '功能一览',
    tipsTitle: '使用技巧',
    faqTitle: '常见问题',
    features: [
      { name: '对话问答', desc: '多轮对话，自动记住用户偏好与历史' },
      { name: '联网搜索', desc: '实时搜索最新信息与新闻' },
      { name: '图片/视频生成', desc: '一句话生成图片与视频' },
      { name: '出行比价', desc: '机票/火车票跨平台比价' },
      { name: '地图服务', desc: '地理编码、天气、路径规划与周边搜索' },
      { name: '论文搜索', desc: 'arXiv 论文检索与 PDF 下载链接' },
      { name: '编程与竞赛', desc: 'LeetCode 每日一题、题目、题解与提交' },
      { name: '网页抓取', desc: '抓取网页内容并转为可读文本' },
      { name: '美食菜谱', desc: '菜谱查询与智能推荐' },
      { name: '文件操作', desc: '受限文件系统的读取与写入' },
    ],
    tips: [
      'Enter 发送消息，Shift+Enter 换行',
      '会话右侧的 ... 支持重命名、置顶、删除',
      '侧边栏右边缘可拖拽调整宽度',
      '在系统设置中可切换浅色/深色主题与中英文界面',
      '回答中的图片与视频会直接渲染显示',
    ],
    faq: [
      {
        q: '为什么图片/视频生成需要等待？',
        a: '部分生成任务在后台异步执行，完成后会自动展示在回答中，请耐心等待。',
      },
      {
        q: '助手会记住我的偏好吗？',
        a: '会。系统会把关键信息写入长期记忆，下次对话时自动引用。',
      },
      {
        q: '如何开始一个新的对话？',
        a: '点击左侧「+ 新对话」即可；侧边栏收起时，左上角也有悬浮的 + 按钮。',
      },
    ],
  },
  auth: {
    login: '登录',
    register: '注册',
    email: '邮箱',
    password: '密码',
    toRegister: '没有账号？注册',
    toLogin: '已有账号？登录',
  },
}

export type TranslationKey = typeof zh

const en: TranslationKey = {
  sidebar: {
    newChat: '+ New Chat',
    pinned: 'Pinned',
    today: 'Today',
    within7: 'Last 7 days',
    within30: 'Last 30 days',
    older: 'Over 30 days',
    untitled: 'Untitled',
    rename: 'Rename',
    pin: 'Pin',
    unpin: 'Unpin',
    delete: 'Delete',
    logout: 'Log out',
    settings: 'Settings',
    help: 'Help',
    expand: 'Expand sidebar',
    collapse: 'Collapse sidebar',
    sessionActions: 'Session actions',
    userMenu: 'User menu',
  },
  welcome: {
    intro1:
      'Hi, I am your personal all-in-one assistant, able to complete all kinds of tasks through tool calls.',
    intro2: 'Ask me “What can you do” and I will show you every feature I offer.',
    features: {
      search: { title: 'Web Search', desc: 'Search the latest info & news' },
      media: { title: 'Image/Video', desc: 'Generate images & videos from text' },
      map: { title: 'Map Service', desc: 'Geocoding, weather, routes & POIs' },
      code: { title: 'Coding & Contest', desc: 'LeetCode problems, solutions & stats' },
    },
  },
  chat: {
    inputPlaceholder: 'Type your message…',
    send: 'Send',
    copy: 'Copy',
    copied: 'Copied',
    thinking: 'Thinking…',
  },
  tool: {
    call: 'Calling',
    running: 'Running',
    success: 'Done',
    failed: 'Failed',
  },
  settings: {
    title: 'Settings',
    helpTitle: 'Help',
    theme: 'Theme',
    light: 'Light',
    dark: 'Dark',
    language: 'Language',
    chinese: '中文',
    english: 'English',
    close: 'Close',
  },
  help: {
    featuresTitle: 'Features',
    tipsTitle: 'Tips',
    faqTitle: 'FAQ',
    features: [
      { name: 'Chat', desc: 'Multi-turn conversations with remembered preferences' },
      { name: 'Web Search', desc: 'Search the latest info & news in real time' },
      { name: 'Image/Video', desc: 'Generate images & videos from text' },
      { name: 'Travel Deals', desc: 'Compare flights & train tickets across platforms' },
      { name: 'Map Service', desc: 'Geocoding, weather, routes & nearby POIs' },
      { name: 'Paper Search', desc: 'arXiv paper search with PDF download links' },
      { name: 'Coding & Contest', desc: 'LeetCode daily problem, solutions & submissions' },
      { name: 'Web Fetch', desc: 'Fetch web pages and convert to readable text' },
      { name: 'Recipes', desc: 'Recipe lookup and smart recommendations' },
      { name: 'Files', desc: 'Read & write within a restricted file system' },
    ],
    tips: [
      'Enter to send, Shift+Enter for a new line',
      'The ... button on a session supports rename, pin & delete',
      'Drag the right edge of the sidebar to resize it',
      'Switch light/dark theme and Chinese/English in Settings',
      'Images and videos in answers are rendered directly',
    ],
    faq: [
      {
        q: 'Why does image/video generation take a while?',
        a: 'Some generation tasks run asynchronously in the background and appear in the answer when done.',
      },
      {
        q: 'Does the assistant remember my preferences?',
        a: 'Yes. Key info is stored in long-term memory and auto-referenced in later conversations.',
      },
      {
        q: 'How do I start a new conversation?',
        a: 'Click “+ New Chat” on the left; when the sidebar is collapsed, use the floating + button.',
      },
    ],
  },
  auth: {
    login: 'Log in',
    register: 'Sign up',
    email: 'Email',
    password: 'Password',
    toRegister: 'No account? Sign up',
    toLogin: 'Have an account? Log in',
  },
}

// 语言 → 文案字典
export const translations: Record<Locale, TranslationKey> = { zh, en }
