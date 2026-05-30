<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="topbar-inner">
        <a class="brand" href="#composer" aria-label="回到视频链接输入">
          <img class="brand-mark" src="/logo.png" alt="" aria-hidden="true" />
          <span>
            <span class="brand-title">鼠鼠视频下载工具</span>
            <span class="brand-subtitle">目前支持抖音</span>
          </span>
        </a>

        <nav class="desktop-nav" aria-label="主要导航">
          <a class="nav-pill is-active" href="#composer">链接</a>
          <a class="nav-pill" href="#formats">下载格式</a>
        </nav>
      </div>
    </header>

    <main class="workspace">
      <section class="workspace-hero" aria-labelledby="page-title">
        <div class="hero-copy">
          <h1 id="page-title">免费视频下载</h1>
          <p>粘贴视频链接后解析可用格式，选择视频或音频版本并下载。</p>
        </div>
      </section>

      <section id="composer" class="composer-panel" aria-labelledby="composer-title">
        <div class="section-heading compact">
          <span class="eyebrow">第一步</span>
          <h2 id="composer-title">粘贴视频链接</h2>
        </div>

        <div class="link-composer">
          <div class="composer-input-wrap">
            <Search :size="20" aria-hidden="true" />
            <input
              v-model.trim="videoUrl"
              class="composer-input"
              placeholder="粘贴抖音分享文案或 https://v.douyin.com/..."
              aria-label="视频链接"
              @keydown.enter="parseVideo"
            />
          </div>
          <button class="btn btn-primary btn-large" type="button" :disabled="parseLoading || !videoUrl" @click="parseVideo">
            <Search :size="18" />
            {{ parseLoading ? '解析中' : '解析' }}
          </button>
        </div>

        <div v-if="parseError" class="notice danger">
          <strong>解析失败</strong>
          <span>{{ parseError }}</span>
        </div>
      </section>

      <section id="formats" class="panel flow-panel" aria-labelledby="video-title">
        <div class="section-heading">
          <div>
            <span class="eyebrow">解析结果</span>
            <h2 id="video-title">视频信息与下载格式</h2>
          </div>
        </div>

        <div v-if="parseLoading" class="loading-block" aria-live="polite">
          <div class="skeleton thumb-skeleton"></div>
          <div class="skeleton-lines">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>

        <div v-else-if="!video" class="empty-state">
          <div class="empty-mark">01</div>
          <div>
            <h3>先解析一个链接</h3>
            <p>解析后这里会显示标题、封面、平台、可下载格式和文件大小。</p>
          </div>
        </div>

        <template v-else>
          <div class="video-summary">
            <img v-if="video.thumbnail" class="thumbnail" :src="proxiedImage(video.thumbnail)" :alt="video.title" />
            <div v-else class="thumbnail placeholder" aria-hidden="true"></div>

            <div class="video-copy">
              <div class="video-kicker">
                <span class="chip chip-strong">{{ video.platform || '未知平台' }}</span>
                <span v-if="video.duration" class="chip">{{ formatDuration(video.duration) }}</span>
              </div>
              <h3>{{ video.title }}</h3>
              <div class="meta-row">
                <span v-if="video.author">{{ video.author }}</span>
                <span v-if="video.view_count">{{ formatNumber(video.view_count) }} 次播放</span>
                <span>{{ formatCount }} 个格式</span>
              </div>
            </div>
          </div>

          <div class="format-toolbar">
            <div>
              <span class="eyebrow">选择格式</span>
              <p>选择一个目标格式后下载。</p>
            </div>
          </div>

          <div class="format-list" role="radiogroup" aria-label="下载格式">
            <button
              v-for="format in visibleFormats"
              :key="format.id + format.kind"
              class="format-row"
              :class="{ 'is-selected': selectedFormatId === format.id }"
              type="button"
              role="radio"
              :aria-checked="selectedFormatId === format.id"
              @click="selectedFormatId = format.id"
            >
              <span class="radio-dot" aria-hidden="true"></span>
              <span class="format-main">
                <strong>{{ format.label }}</strong>
                <span>{{ format.note || format.kind }}</span>
              </span>
              <span class="chip">{{ format.filesize_text || '未知大小' }}</span>
            </button>
          </div>

          <div class="download-bar">
            <div>
              <span class="eyebrow">下载目标</span>
              <strong>{{ selectedFormat?.label || '未选择格式' }}</strong>
            </div>
            <button class="btn btn-primary" type="button" :disabled="downloadLoading || !selectedFormat" @click="startDownload">
              <Download :size="17" />
              {{ downloadLoading ? '创建中' : '下载' }}
            </button>
          </div>

          <div v-if="downloadMessage" class="notice info">
            <strong>已准备</strong>
            <span>
              {{ downloadMessage }}
              <a v-if="downloadLink" class="notice-link" :href="downloadLink" target="_blank" rel="noopener noreferrer">
                手动打开下载链接
              </a>
            </span>
          </div>
          <div v-if="downloadError" class="notice danger">
            <strong>下载失败</strong>
            <span>{{ downloadError }}</span>
          </div>
        </template>
      </section>
    </main>

    <nav class="mobile-nav" aria-label="移动端导航">
      <a href="#composer"><Search :size="18" /><span>链接</span></a>
      <a href="#formats"><Download :size="18" /><span>格式</span></a>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { Download, Search } from '@lucide/vue';
import { absoluteApiUrl, api } from './api';

type VideoFormat = {
  id: string;
  label: string;
  kind: 'video' | 'audio';
  filesize_text: string;
  note: string;
};

type VideoInfo = {
  title: string;
  webpage_url: string;
  thumbnail: string | null;
  author: string | null;
  duration: number | null;
  view_count: number | null;
  platform: string | null;
  formats: VideoFormat[];
};

const videoUrl = ref('');
const video = ref<VideoInfo | null>(null);
const selectedFormatId = ref('');
const parseLoading = ref(false);
const parseError = ref('');
const downloadLoading = ref(false);
const downloadMessage = ref('');
const downloadError = ref('');
const downloadLink = ref('');

const selectedFormat = computed(() => video.value?.formats.find((item) => item.id === selectedFormatId.value) || null);
const visibleFormats = computed(() => video.value?.formats || []);
const formatCount = computed(() => video.value?.formats.length || 0);

function apiError(error: unknown) {
  const maybe = error as { response?: { data?: { detail?: string } }; message?: string };
  return maybe.response?.data?.detail || maybe.message || '请求失败';
}

async function parseVideo() {
  if (!videoUrl.value || parseLoading.value) return;
  parseLoading.value = true;
  parseError.value = '';
  downloadMessage.value = '';
  downloadError.value = '';
  downloadLink.value = '';
  try {
    const { data } = await api.post('/api/parse', { url: videoUrl.value });
    video.value = data.video;
    selectedFormatId.value = video.value?.formats[0]?.id || '';
  } catch (error) {
    video.value = null;
    selectedFormatId.value = '';
    parseError.value = apiError(error);
  } finally {
    parseLoading.value = false;
  }
}

async function startDownload() {
  if (!selectedFormat.value || !video.value) return;
  const downloadWindow = createDownloadWindow();
  downloadLoading.value = true;
  downloadError.value = '';
  downloadMessage.value = '';
  downloadLink.value = '';
  try {
    const { data } = await api.post('/api/download', {
      url: video.value.webpage_url || videoUrl.value,
      format_id: selectedFormat.value.id,
      kind: selectedFormat.value.kind,
    });
    const url = absoluteApiUrl(data.download_url);
    downloadLink.value = url;
    openDownloadUrl(url, downloadWindow);
    downloadMessage.value = '下载已打开；如果浏览器没有反应，请点这里。';
  } catch (error) {
    closeDownloadWindow(downloadWindow);
    downloadError.value = apiError(error);
  } finally {
    downloadLoading.value = false;
  }
}

function createDownloadWindow() {
  const target = window.open('', '_blank');
  if (!target) return null;
  try {
    target.document.title = '下载准备中';
    target.document.body.style.margin = '0';
    target.document.body.style.fontFamily = '-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';
    target.document.body.innerHTML =
      '<main style="min-height:100vh;display:grid;place-items:center;padding:24px;color:#2f2419;background:#fbf7ef;">下载准备中，请稍候...</main>';
  } catch {
    // Some browsers restrict writes to newly opened tabs; navigation below still works.
  }
  return target;
}

function closeDownloadWindow(target: Window | null) {
  if (target && !target.closed) {
    target.close();
  }
}

function openDownloadUrl(url: string, target: Window | null) {
  if (target && !target.closed) {
    target.location.href = url;
    return;
  }
  window.location.assign(url);
}

function formatDuration(seconds: number) {
  const value = Math.max(0, Math.floor(seconds));
  const h = Math.floor(value / 3600);
  const m = Math.floor((value % 3600) / 60);
  const s = value % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN', { notation: 'compact' }).format(value);
}

function proxiedImage(url: string) {
  return absoluteApiUrl(`/api/image-proxy?url=${encodeURIComponent(url)}`);
}
</script>
