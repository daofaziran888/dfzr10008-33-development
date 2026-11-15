<template>
  <section class="page" data-module="feedback">
    <header class="page-head">
      <div>
        <h2>数据质量反馈管理</h2>
        <p class="page-desc">
          按时间串起数据产品、反馈类型、严重程度、处理状态与解决结论；未解决的高严重度反馈会冻结产品的认证与发布准入。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记反馈记录</button>
        <button class="btn" type="button" @click="exportRows">导出数据质量反馈清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>数据产品</span>
        <input v-model="filters.product" placeholder="按产品名称或产品编号检索" />
      </label>
      <label class="filter-item">
        <span>严重程度</span>
        <select v-model="filters.severity">
          <option value="">全部</option>
          <option v-for="item in severities" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>处理状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>准入结果</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          :class="{ 'row-active': selected && selected.id === row.id }"
          @click="selectRow(row)"
        >
          <td v-for="column in columns" :key="column">
            <span v-if="column === '严重程度'" class="pill" :class="severityClass(row[column])">{{ row[column] ?? '—' }}</span>
            <span v-else-if="column === '处理状态'" class="pill" :class="statusClass(row[column])">{{ row[column] ?? '—' }}</span>
            <template v-else>{{ row[column] || '—' }}</template>
          </td>
          <td>
            <span class="pill" :class="gateClass(row)">{{ gateLabel(row) }}</span>
          </td>
          <td class="row-actions" @click.stop>
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无数据质量反馈数据，可先登记反馈记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条数据质量反馈记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section v-if="selected" class="trail-panel" data-module="feedback-trajectory">
      <header class="trail-head">
        <div>
          <h3>质量反馈轨迹 · {{ selected['反馈编号'] || '未编号反馈' }}</h3>
          <p class="page-desc">
            {{ selected['数据产品'] || '未关联产品' }} · {{ selected['反馈类型'] || '未分类' }}
            · 反馈人 {{ selected['反馈人'] || '—' }} · {{ selected['反馈时间'] || '—' }}
          </p>
        </div>
        <div class="trail-badges">
          <span class="pill" :class="severityClass(selected['严重程度'])">
            严重程度 {{ selected['严重程度'] || '—' }}
          </span>
          <span class="pill" :class="statusClass(selected['处理状态'])">
            {{ selected['处理状态'] || '—' }}
          </span>
        </div>
      </header>

      <div class="trail-body">
        <ol class="timeline">
          <li v-for="(event, index) in timelineEvents" :key="`${event.时间}-${index}`" class="timeline-item">
            <span class="timeline-dot" :class="statusClass(event['处理状态'])"></span>
            <div class="timeline-card">
              <div class="timeline-meta">
                <strong>{{ event['动作'] }}</strong>
                <span class="pill" :class="statusClass(event['处理状态'])">{{ event['处理状态'] }}</span>
                <span class="pill" :class="severityClass(event['严重程度'])">严重度 {{ event['严重程度'] }}</span>
                <time>{{ event['时间'] }}</time>
                <span class="timeline-operator">{{ event['操作人'] }}</span>
              </div>
              <p class="timeline-note">{{ event['说明'] || '—' }}</p>
            </div>
          </li>
        </ol>

        <aside class="trail-side">
          <article class="trail-card">
            <h4>解决结论</h4>
            <p v-if="selected['解决结论']" class="trail-text">{{ selected['解决结论'] }}</p>
            <p v-else class="trail-text muted">
              尚未记录解决轨迹，{{ selected['是否未解决'] ? '问题仍在处理中' : '关闭前需要补齐' }}。
            </p>
            <p v-if="selected['解决人']" class="trail-text muted">
              解决人 {{ selected['解决人'] }} · {{ selected['解决时间'] || '—' }}
            </p>
          </article>

          <article class="trail-card">
            <h4>产品准入</h4>
            <div class="trail-gate" :class="gateClass(selected)">
              <span class="pill" :class="gateClass(selected)">
                {{ selected['产品准入']?.['准入结果'] || '—' }}
              </span>
              <span class="trail-text">未解决反馈 {{ selected['产品准入']?.['未解决反馈数量'] ?? 0 }} 条</span>
            </div>
            <p v-if="selected['产品准入']?.['冻结原因']" class="trail-text error-text">
              {{ selected['产品准入']['冻结原因'] }}
            </p>
            <p v-else class="trail-text muted">认证准入与发布准入均可继续。</p>
            <ul v-if="blockers.length" class="trail-blockers">
              <li v-for="blocker in blockers" :key="blocker['反馈编号']">
                {{ blocker['反馈编号'] }} · {{ blocker['反馈类型'] }} · 严重程度 {{ blocker['严重程度'] }}
              </li>
            </ul>
          </article>

          <article class="trail-card">
            <h4>严重度判定历史</h4>
            <p class="trail-text muted">状态变化保留当时的严重度判定，后续修改不会覆盖历史记录。</p>
            <ul class="trail-blockers">
              <li v-for="(item, index) in severityHistory" :key="`${item.时间}-${index}`">
                {{ item.时间 }} · {{ item.严重程度 }} · {{ item.判定人 }}
                <span class="muted">（{{ item.说明 }}）</span>
              </li>
            </ul>
          </article>
        </aside>
      </div>
    </section>

    <form v-if="dialog.open" class="action-dialog" @submit.prevent="submitAction">
      <h3>{{ dialog.action }} · {{ dialog.row?.['反馈编号'] }}</h3>
      <p class="page-desc">
        {{ dialog.action === '关闭反馈'
          ? '关闭反馈必须写明解决轨迹：问题定位、修复动作与验证结果。'
          : '补充解决轨迹会记录在当前反馈的时间轴上。' }}
      </p>
      <label class="dialog-field">
        <span>操作人</span>
        <input v-model="dialog.operator" placeholder="填写处理人" />
      </label>
      <label class="dialog-field">
        <span>解决轨迹</span>
        <textarea v-model="dialog.resolution" rows="4" placeholder="例如：补充统一社会信用代码字段映射并回归验证通过"></textarea>
      </label>
      <div class="dialog-actions">
        <button class="btn primary" type="submit">提交</button>
        <button class="btn ghost" type="button" @click="closeDialog">取消</button>
      </div>
    </form>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

type TimelineEvent = {
  时间: string
  动作: string
  处理状态: string
  严重程度: string
  操作人: string
  说明: string
}

const ENDPOINT = '/api/feedback'
const columns = ['反馈编号', '数据产品', '反馈类型', '严重程度', '处理状态', '反馈时间', '解决结论']
const statuses = ['待处理', '处理中', '已解决', '已关闭']
const severities = ['高', '中', '低']
const stats = ref([
  { label: '反馈记录总数', value: 0 },
  { label: '处理中反馈', value: 0 },
  { label: '未解决高严重度', value: 0 },
  { label: '冻结准入产品', value: 0 },
])

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = reactive({ product: '', severity: '', status: '' })
const selected = ref<Row | null>(null)
const dialog = reactive({
  open: false,
  action: '',
  row: null as Row | null,
  operator: '',
  resolution: '',
})

const timelineEvents = computed<TimelineEvent[]>(() => {
  const events = (selected.value?.['时间轴'] ?? []) as TimelineEvent[]
  return [...events].sort((a, b) => String(a.时间).localeCompare(String(b.时间)))
})
const blockers = computed<Row[]>(() => selected.value?.['产品准入']?.['阻断反馈'] ?? [])
const severityHistory = computed<Row[]>(() => {
  const history = selected.value?.['严重度判定历史'] ?? []
  return history.length
    ? history
    : [{ 时间: selected.value?.['反馈时间'], 严重程度: selected.value?.['严重程度'], 判定人: selected.value?.['反馈人'], 说明: '提交反馈时判定' }]
})

function severityClass(severity?: string) {
  return {
    高: 'pill-danger',
    中: 'pill-warning',
    低: 'pill-neutral',
  }[severity ?? ''] ?? 'pill-neutral'
}

function statusClass(status?: string) {
  return {
    待处理: 'pill-neutral',
    处理中: 'pill-warning',
    已解决: 'pill-success',
    已关闭: 'pill-success',
  }[status ?? ''] ?? 'pill-neutral'
}

function gateClass(row: Row) {
  return row?.['产品准入']?.['准入结果'] === '冻结' ? 'pill-danger' : 'pill-success'
}

function gateLabel(row: Row) {
  return row?.['产品准入']?.['准入结果'] ?? '—'
}

function availableActions(row: Row) {
  const status = row?.['处理状态']
  const actions: string[] = []
  if (status === '待处理') actions.push('开始处理')
  if (status === '待处理' || status === '处理中') actions.push('补充解决轨迹', '标记解决')
  if (status === '已解决') actions.push('关闭反馈')
  return actions
}

function selectRow(row: Row) {
  selected.value = row
}

function resetFilters() {
  filters.product = ''
  filters.severity = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = ''
  noticeMessage.value = '反馈登记入口尚未接入审批流，可先用接口提交反馈记录'
}

function closeDialog() {
  dialog.open = false
  dialog.action = ''
  dialog.row = null
  dialog.operator = ''
  dialog.resolution = ''
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  if (action === '补充解决轨迹' || action === '关闭反馈') {
    dialog.open = true
    dialog.action = action
    dialog.row = row
    dialog.operator = ''
    dialog.resolution = ''
    return
  }
  await submitRequest(action, row, {})
}

async function submitAction() {
  if (!dialog.row) return
  const values: Record<string, string> = { action: dialog.action }
  if (dialog.operator.trim()) values['操作人'] = dialog.operator.trim()
  if (dialog.resolution.trim()) values['解决轨迹'] = dialog.resolution.trim()
  const ok = await submitRequest(dialog.action, dialog.row, values)
  if (ok) closeDialog()
}

async function submitRequest(action: string, row: Row, values: Record<string, string>) {
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ ...values, action }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.message || '数据质量反馈动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message ?? ''
    await reload()
    return true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '数据质量反馈操作失败'
    return false
  }
}

async function loadTrajectory() {
  const query = new URLSearchParams()
  if (filters.product.trim()) query.set('product', filters.product.trim())
  if (filters.severity) query.set('severity', filters.severity)
  if (filters.status) query.set('status', filters.status)
  try {
    const response = await request(`${ENDPOINT}/trajectory?${query.toString()}`)
    if (!response.ok) {
      throw new Error('质量反馈轨迹读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    const current = selected.value
    const matched = current ? rows.value.find((row) => row.id === current.id) : null
    selected.value = matched ?? rows.value[0] ?? null
    updateStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '数据质量反馈列表读取失败'
  }
}

function updateStats() {
  const frozenProducts = new Set<string>()
  let highUnresolved = 0
  let inProgress = 0
  for (const row of rows.value) {
    if (row['处理状态'] === '处理中') inProgress += 1
    if (row['是否未解决'] && row['严重程度'] === '高') highUnresolved += 1
    if (row['产品准入']?.['准入结果'] === '冻结') {
      frozenProducts.add(row['关联产品编号'] || row['数据产品'])
    }
  }
  stats.value = [
    { label: '反馈记录总数', value: total.value },
    { label: '处理中反馈', value: inProgress },
    { label: '未解决高严重度', value: highUnresolved },
    { label: '冻结准入产品', value: frozenProducts.size },
  ]
}

async function reload() {
  errorMessage.value = ''
  await loadTrajectory()
}

onMounted(reload)
</script>
