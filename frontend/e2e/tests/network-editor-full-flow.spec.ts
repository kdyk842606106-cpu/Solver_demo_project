import { test, expect } from '@playwright/test'

const machineTypes = [
  { id: 1, code: 'EDITOR_FLOW', name: 'Editor Flow Machine', description: 'Full editor flow fixture' },
]

const stateFeatureDefs = [
  {
    id: 1,
    machine_type_id: 1,
    feature_key: 'fixture_dim_ready',
    feature_name: 'Fixture Ready',
    value_type: 'enum',
    allowed_values: ['false', 'true'],
  },
  {
    id: 2,
    machine_type_id: 1,
    feature_key: 'fixture_dim_done',
    feature_name: 'Fixture Done',
    value_type: 'enum',
    allowed_values: ['false', 'true'],
  },
]

function templateFeatureKey(featureKey: string) {
  if (featureKey === 'fixture_ready') return 'fixture_dim_ready'
  if (featureKey === 'fixture_done') return 'fixture_dim_done'
  return featureKey
}

const emptyGraph = {
  machine_type_id: 1,
  revision: 'editor-full-flow-revision',
  view_mode: 'state_transition',
  state_nodes: [],
  activity_nodes: [],
  bindings: [],
  edges: [],
  summary: {
    state_node_count: 0,
    state_instance_count: 0,
    state_reference_instance_count: 0,
    state_package_count: 0,
    atomic_state_count: 0,
    activity_node_count: 0,
    executable_activity_count: 0,
    edge_count: 0,
    coverage_gap_count: 0,
    cross_level_binding_count: 0,
    blocking_count: 0,
  },
  validation_summary: {
    blocking_count: 0,
    warning_count: 0,
    issue_count: 0,
  },
}

async function routeEditorFlowFixture(page: any) {
  await page.route(/\/(health|api\/v1\/)/, async (route: any, request: any) => {
    const url = request.url()
    const method = request.method()

    if (url.endsWith('/health')) {
      await route.fulfill({ status: 200, body: JSON.stringify({ status: 'ok', version: 'test' }) })
      return
    }

    if (url.endsWith('/api/v1/machine-types')) {
      await route.fulfill({ status: 200, body: JSON.stringify(machineTypes) })
      return
    }

    if (url.endsWith('/api/v1/machines')) {
      await route.fulfill({ status: 200, body: JSON.stringify([]) })
      return
    }

    if (url.includes('/api/v1/resources') || url.endsWith('/api/v1/features')) {
      await route.fulfill({ status: 200, body: JSON.stringify([]) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/feature-defs')) {
      await route.fulfill({ status: 200, body: JSON.stringify(stateFeatureDefs) })
      return
    }

    if (
      url.endsWith('/api/v1/machine-types/1/state-nodes') ||
      url.endsWith('/api/v1/machine-types/1/activity-nodes') ||
      url.endsWith('/api/v1/machine-types/1/atomic-activities') ||
      url.endsWith('/api/v1/machine-types/1/state-node-references') ||
      url.endsWith('/api/v1/machine-types/1/activity-state-bindings') ||
      url.endsWith('/api/v1/machine-types/1/op-rules')
    ) {
      await route.fulfill({ status: 200, body: JSON.stringify([]) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/network-editor/graph') && method === 'POST') {
      await route.fulfill({ status: 200, body: JSON.stringify(emptyGraph) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/network-editor/validate') && method === 'POST') {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          machine_type_id: 1,
          status: 'ready',
          summary: {
            modeling_issue_count: 0,
            solver_ready_issue_count: 0,
            blocking_count: 0,
            warning_count: 0,
            issue_count: 0,
          },
          modeling_issues: [],
          solver_ready_issues: [],
        }),
      })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/network-editor/impact') && method === 'POST') {
      await route.fulfill({ status: 404, body: JSON.stringify({ code: 'HTTP_404', detail: 'No impact fixture' }) })
      return
    }

    if (url.endsWith('/api/v1/machine-types/1/network-editor/commit') && method === 'POST') {
      const body = JSON.parse(request.postData() || '{}')
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          machine_type_id: 1,
          applied_change_count: body.changes?.length || 0,
          results: [],
          validation: {
            machine_type_id: 1,
            status: 'ready',
            summary: {
              modeling_issue_count: 0,
              solver_ready_issue_count: 0,
              blocking_count: 0,
              warning_count: 0,
              issue_count: 0,
            },
            modeling_issues: [],
            solver_ready_issues: [],
          },
          revision: 'editor-full-flow-after-commit',
        }),
      })
      return
    }

    await route.fulfill({ status: 200, body: JSON.stringify({}) })
  })
}

async function openNetworkEditor(page: any) {
  await page.goto('/')
  await page.waitForSelector('.el-header', { timeout: 10000 })
  await page.locator('.el-tabs__item:has-text("网络编辑器")').click()
  await expect(page.getByTestId('network-editor')).toBeVisible()
  await page.getByTestId('network-editor-machine-type-select').locator('.el-select__wrapper').click()
  await page.locator('.el-select-dropdown:visible .el-select-dropdown__item', {
    hasText: 'Editor Flow Machine (EDITOR_FLOW)',
  }).click()
  const depthInputs = page.getByRole('spinbutton')
  for (const index of [0, 1]) {
    await depthInputs.nth(index).fill('0')
    await depthInputs.nth(index).press('Enter')
  }
  await expect(page.locator('.el-loading-mask')).toBeHidden({ timeout: 10000 })
  await expect(page.getByTestId('network-editor-canvas')).toBeVisible()
  await expect(page.getByTestId('network-editor-x6-canvas')).toBeVisible()
}

async function openCreateMenuItem(page: any, testId: string) {
  await expect(page.locator('.el-overlay.is-drawer:visible')).toHaveCount(0)
  await page.getByTestId('network-editor-create-menu').click()
  const item = page.getByTestId(testId).last()
  await expect(item).toBeVisible()
  await item.click()
}

async function collapsePropertiesPane(page: any) {
  const pane = page.getByTestId('network-editor-properties-pane')
  await expect(pane).toBeVisible()
  const collapsed = await pane.evaluate((element: HTMLElement) => element.classList.contains('collapsed'))
  if (!collapsed) {
    await page.getByTestId('network-editor-properties-pane-toggle').click()
    await page.waitForTimeout(120)
  }
}

async function createAtomicState(page: any, name: string, featureKey: string, expectedDraftId: string) {
  await openCreateMenuItem(page, 'network-editor-create-state')
  const drawer = page.getByTestId('network-editor-state-drawer')
  await expect(drawer).toBeVisible()
  await drawer.locator('.el-form-item').nth(1).locator('input').fill(name)
  await chooseElSelectOption(page, drawer.getByTestId('network-editor-state-feature'), templateFeatureKey(featureKey))
  await chooseElSelectOption(page, drawer.getByTestId('network-editor-state-target-value'), 'true')
  await drawer.getByTestId('network-editor-state-drawer-save').click()
  await expect(drawer).toBeHidden()
  await expect(page.locator('.el-overlay.is-drawer:visible')).toHaveCount(0)
  const node = page.getByTestId(`network-editor-state-node-${expectedDraftId}`)
  await expect(node).toHaveCount(0)
  await expect(page.locator('.draft-change-list')).toContainText(name)
  return node
}

async function createAggregateState(page: any, name: string, expectedDraftId: string) {
  await openCreateMenuItem(page, 'network-editor-create-state')
  const drawer = page.getByTestId('network-editor-state-drawer')
  await expect(drawer).toBeVisible()
  await chooseStateKind(drawer, 'aggregate')
  await drawer.locator('.el-form-item').nth(1).locator('input').fill(name)
  await drawer.getByTestId('network-editor-state-drawer-save').click()
  await expect(drawer).toBeHidden()
  await expect(page.locator('.el-overlay.is-drawer:visible')).toHaveCount(0)
  const node = page.getByTestId(`network-editor-state-node-${expectedDraftId}`)
  await expect(node).toBeVisible()
  await expect(node).toContainText(name)
  return node
}

async function createAtomicActivity(page: any, name: string, expectedDraftId: string) {
  await openCreateMenuItem(page, 'network-editor-create-atomic')
  const drawer = page.getByTestId('network-editor-atomic-drawer')
  await expect(drawer).toBeVisible()
  await drawer.locator('.el-form-item').nth(1).locator('input').fill(name)
  await drawer.getByTestId('network-editor-atomic-drawer-save').click()
  await expect(drawer).toBeHidden()
  await expect(page.locator('.el-overlay.is-drawer:visible')).toHaveCount(0)
  await expect(page.getByTestId(`network-editor-activity-node-${expectedDraftId}`)).toHaveCount(0)
  const draftRow = page.locator('.draft-change-row', { hasText: name })
  await expect(draftRow).toBeVisible()
  return draftRow
}

async function openBlankContextMenu(page: any, offsetX: number, offsetY: number) {
  const canvas = page.getByTestId('network-editor-x6-canvas')
  const canvasBox = await locatorClientRect(canvas, { preferOwnRect: true })
  const screenX = canvasBox.x + offsetX
  const screenY = canvasBox.y + offsetY
  await canvas.click({ button: 'right', position: { x: offsetX, y: offsetY } })
  const menu = page.getByTestId('network-editor-blank-context-menu')
  await expect(menu).toBeVisible()
  return { menu, screenX, screenY }
}

async function createStateFromOpenDrawer(page: any, name: string, featureKey: string, stateKind = 'atomic') {
  const drawer = page.getByTestId('network-editor-state-drawer')
  await expect(drawer).toBeVisible()
  if (stateKind === 'aggregate') await chooseStateKind(drawer, 'aggregate')
  await drawer.locator('.el-form-item').nth(1).locator('input').fill(name)
  if (stateKind !== 'aggregate') {
    await chooseElSelectOption(page, drawer.getByTestId('network-editor-state-feature'), templateFeatureKey(featureKey))
    await chooseElSelectOption(page, drawer.getByTestId('network-editor-state-target-value'), 'true')
  }
  await drawer.getByTestId('network-editor-state-drawer-save').click()
  await expect(drawer).toBeHidden()
  await expect(page.locator('.el-overlay.is-drawer:visible')).toHaveCount(0)
}

async function createAtomicActivityFromOpenDrawer(page: any, name: string) {
  const drawer = page.getByTestId('network-editor-atomic-drawer')
  await expect(drawer).toBeVisible()
  await drawer.locator('.el-form-item').nth(1).locator('input').fill(name)
  await drawer.getByTestId('network-editor-atomic-drawer-save').click()
  await expect(drawer).toBeHidden()
  await expect(page.locator('.el-overlay.is-drawer:visible')).toHaveCount(0)
}

function expectLayoutNear(layout: any, x: number, y: number) {
  expect(Math.abs(Number(layout?.x) - x)).toBeLessThan(40)
  expect(Math.abs(Number(layout?.y) - y)).toBeLessThan(40)
}

async function leftDragBlankCanvas(page: any, startOffsetX: number, startOffsetY: number, deltaX: number, deltaY: number) {
  const point = await visibleBlankPointInX6Canvas(page, startOffsetX, startOffsetY)
  await leftDragFromScreenPoint(page, point.x, point.y, deltaX, deltaY)
}

async function leftDragFromScreenPoint(page: any, startX: number, startY: number, deltaX: number, deltaY: number) {
  const canvas = page.getByTestId('network-editor-x6-canvas')
  await page.mouse.move(startX, startY)
  await page.mouse.down({ button: 'left' })
  await page.waitForTimeout(180)
  await expect(canvas).not.toHaveClass(/is-canvas-panning/)
  await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 12 })
  await expect(canvas).toHaveClass(/is-canvas-panning/)
  await page.mouse.up({ button: 'left' })
  await expect(canvas).not.toHaveClass(/is-canvas-panning/)
}

async function visibleBlankPointInX6Canvas(page: any, offsetX: number, offsetY: number) {
  const canvas = page.getByTestId('network-editor-x6-canvas')
  await expect(canvas).toBeVisible()
  const point = await canvas.evaluate((element: HTMLElement, preferred: { offsetX: number, offsetY: number }) => {
    const rect = element.getBoundingClientRect()
    const visibleRect = {
      left: Math.max(rect.left, 0),
      top: Math.max(rect.top, 0),
      right: Math.min(rect.right, window.innerWidth),
      bottom: Math.min(rect.bottom, window.innerHeight),
    }
    for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
      const style = window.getComputedStyle(ancestor)
      if (!/(auto|scroll|hidden|clip)/.test(`${style.overflow} ${style.overflowX} ${style.overflowY}`)) continue
      const ancestorRect = ancestor.getBoundingClientRect()
      visibleRect.left = Math.max(visibleRect.left, ancestorRect.left)
      visibleRect.top = Math.max(visibleRect.top, ancestorRect.top)
      visibleRect.right = Math.min(visibleRect.right, ancestorRect.right)
      visibleRect.bottom = Math.min(visibleRect.bottom, ancestorRect.bottom)
    }
    if (visibleRect.right - visibleRect.left < 32 || visibleRect.bottom - visibleRect.top < 32) return null
    const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)
    const visibleWidth = visibleRect.right - visibleRect.left
    const visibleHeight = visibleRect.bottom - visibleRect.top
    const candidates = [
      [rect.left + preferred.offsetX, rect.top + preferred.offsetY],
      [visibleRect.left + visibleWidth * 0.82, visibleRect.top + visibleHeight * 0.18],
      [visibleRect.left + visibleWidth * 0.18, visibleRect.top + visibleHeight * 0.82],
      [visibleRect.left + visibleWidth * 0.5, visibleRect.top + visibleHeight * 0.88],
      [visibleRect.left + visibleWidth * 0.88, visibleRect.top + visibleHeight * 0.5],
      [visibleRect.left + visibleWidth * 0.5, visibleRect.top + visibleHeight * 0.5],
    ]
    let fallback: { x: number, y: number } | null = null
    for (const [candidateX, candidateY] of candidates) {
      const x = clamp(candidateX, visibleRect.left + 16, visibleRect.right - 16)
      const y = clamp(candidateY, visibleRect.top + 16, visibleRect.bottom - 16)
      const hit = document.elementFromPoint(x, y) as HTMLElement | null
      if (!hit || !element.contains(hit)) continue
      fallback ||= { x, y }
      if (hit.closest('[data-cell-id], .x6-node, .x6-edge, [data-action], .semantic-port')) continue
      return { x, y }
    }
    return fallback
  }, { offsetX, offsetY })
  expect(point).toBeTruthy()
  return point
}

async function leftHoldLocatorWithoutDrag(page: any, locator: any) {
  const canvas = page.getByTestId('network-editor-x6-canvas')
  const point = await visibleLocatorPointInX6Canvas(page, locator)
  await page.mouse.move(point.x, point.y)
  await page.mouse.down({ button: 'left' })
  await page.waitForTimeout(180)
  await expect(canvas).not.toHaveClass(/is-canvas-panning/)
  await page.mouse.up({ button: 'left' })
  await expect(page.getByTestId('network-editor-blank-context-menu')).toHaveCount(0)
}

async function visibleLocatorPointInX6Canvas(page: any, locator: any, position = { x: 0.5, y: 0.5 }) {
  const canvas = page.getByTestId('network-editor-x6-canvas')
  await locator.scrollIntoViewIfNeeded()
  const box = await locatorClientRect(locator, { preferOwnRect: true })
  const canvasBox = await locatorClientRect(canvas, { preferOwnRect: true })
  const visibleLeft = Math.max(box.x, canvasBox.x + 8)
  const visibleTop = Math.max(box.y, canvasBox.y + 8)
  const visibleRight = Math.min(box.x + box.width, canvasBox.x + canvasBox.width - 8)
  const visibleBottom = Math.min(box.y + box.height, canvasBox.y + canvasBox.height - 8)
  expect(visibleRight).toBeGreaterThan(visibleLeft)
  expect(visibleBottom).toBeGreaterThan(visibleTop)
  return {
    x: visibleLeft + (visibleRight - visibleLeft) * position.x,
    y: visibleTop + (visibleBottom - visibleTop) * position.y,
  }
}

async function expectLocatorInsideX6Graph(locator: any) {
  const metrics = await locator.evaluate((element: HTMLElement) => {
    const target = element.closest('[data-cell-id]') || element.closest('.x6-node') || element
    const canvas = element.closest('.x6-network-canvas') as HTMLElement | null
    const graph = (canvas?.querySelector('.x6-graph') || canvas) as HTMLElement | null
    const targetRect = target.getBoundingClientRect()
    const graphRect = graph?.getBoundingClientRect()
    return {
      targetLeft: targetRect.left,
      targetTop: targetRect.top,
      targetRight: targetRect.right,
      targetBottom: targetRect.bottom,
      graphLeft: graphRect?.left || 0,
      graphTop: graphRect?.top || 0,
      graphRight: graphRect?.right || 0,
      graphBottom: graphRect?.bottom || 0,
    }
  })
  expect(metrics.targetLeft).toBeGreaterThanOrEqual(metrics.graphLeft - 2)
  expect(metrics.targetTop).toBeGreaterThanOrEqual(metrics.graphTop - 2)
  expect(metrics.targetRight).toBeLessThanOrEqual(metrics.graphRight + 2)
  expect(metrics.targetBottom).toBeLessThanOrEqual(metrics.graphBottom + 2)
}

async function dragRightPortToLeftPort(page: any, sourceLocator: any, targetLocator: any) {
  await targetLocator.scrollIntoViewIfNeeded()
  await sourceLocator.scrollIntoViewIfNeeded()
  const sourcePoint = await visiblePortCenterInX6Canvas(page, sourceLocator, 'output')
  const targetPoint = await visiblePortCenterInX6Canvas(page, targetLocator, 'input')
  await page.mouse.move(sourcePoint.x, sourcePoint.y)
  await page.waitForTimeout(30)
  await page.mouse.down({ button: 'left' })
  await page.waitForTimeout(30)
  await page.mouse.move(targetPoint.x, targetPoint.y, { steps: 12 })
  await page.mouse.up({ button: 'left' })
}

async function visiblePortCenterInX6Canvas(page: any, locator: any, role: 'input' | 'output') {
  const canvas = page.getByTestId('network-editor-x6-canvas')
  const canvasBox = await locatorClientRect(canvas, { preferOwnRect: true })
  const point = await locator.evaluate((element: HTMLElement, requestedRole: 'input' | 'output') => {
    const selector = requestedRole === 'output'
      ? '.semantic-port[data-port-role="output"], [port-group="out"], [port="output"], [data-port-id="output"]'
      : '.semantic-port[data-port-role="input"], [port-group="in"], [port="input"], [data-port-id="input"]'
    const cell = element.closest('[data-cell-id]') || element.closest('.x6-cell') || element.closest('.x6-node') || element
    const candidates = Array.from(cell.querySelectorAll(selector)) as HTMLElement[]
    const port = candidates.find((candidate) =>
      candidate.getAttribute('port-group') ||
      candidate.getAttribute('port') ||
      candidate.getAttribute('magnet') ||
      candidate.tagName.toLowerCase() === 'circle',
    ) || candidates[0]
    if (!port) return null
    const rect = port.getBoundingClientRect()
    return {
      x: rect.x + rect.width / 2,
      y: rect.y + rect.height / 2,
    }
  }, role)
  expect(point).toBeTruthy()
  return {
    x: Math.min(Math.max(point.x, canvasBox.x + 8), canvasBox.x + canvasBox.width - 8),
    y: Math.min(Math.max(point.y, canvasBox.y + 8), canvasBox.y + canvasBox.height - 8),
  }
}

async function confirmDroppedBinding(page: any) {
  const dialog = page.locator('.el-message-box')
  await expect(dialog).toBeVisible()
  await dialog.locator('.el-button--primary').click()
  await expect(dialog).toBeHidden()
}

async function chooseStateKind(drawer: any, kind: 'aggregate' | 'atomic') {
  const index = kind === 'aggregate' ? 0 : 1
  await drawer.getByTestId('network-editor-state-kind-segmented').locator('.el-segmented__item').nth(index).click()
}

async function chooseElSelectOption(page: any, selectRoot: any, text: string) {
  const input = selectRoot.locator('input').last()
  await input.click({ force: true })
  await input.fill(text)
  const listboxId = await input.getAttribute('aria-controls')
  const option = listboxId
    ? page.locator(`#${listboxId} .el-select-dropdown__item`, { hasText: text }).last()
    : page.locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: text }).last()
  await expect(option).toBeVisible()
  await option.click({ force: true })
  await expect(selectRoot).toContainText(text)
  await page.keyboard.press('Escape')
}

async function locatorClientRect(locator: any, options: { preferOwnRect?: boolean } = {}) {
  await expect(locator).toBeVisible()
  let box = { x: 0, y: 0, width: 0, height: 0 }
  for (let attempt = 0; attempt < 10; attempt += 1) {
    box = await locator.evaluate((element: HTMLElement, preferOwnRect: boolean) => {
      const ownRect = element.getBoundingClientRect()
      const target = preferOwnRect && ownRect.width > 0 && ownRect.height > 0
        ? element
        : element.closest('[data-cell-id]') || element.closest('.x6-node') || element
      const rect = target.getBoundingClientRect()
      return {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      }
    }, !!options.preferOwnRect)
    if (box.width > 0 && box.height > 0) break
    await locator.page().waitForTimeout(50)
  }
  expect(box.width).toBeGreaterThan(0)
  expect(box.height).toBeGreaterThan(0)
  return box
}

async function expectLocatorInside(container: any, child: any) {
  const containerBox = await locatorClientRect(container)
  const childBox = await locatorClientRect(child)
  expect(childBox.x).toBeGreaterThanOrEqual(containerBox.x - 2)
  expect(childBox.y).toBeGreaterThanOrEqual(containerBox.y - 2)
  expect(childBox.x + childBox.width).toBeLessThanOrEqual(containerBox.x + containerBox.width + 2)
  expect(childBox.y + childBox.height).toBeLessThanOrEqual(containerBox.y + containerBox.height + 2)
}

test.describe('Network Editor — full node and edge creation flow', () => {
  test.beforeEach(async ({ page }) => {
    await routeEditorFlowFixture(page)
    await openNetworkEditor(page)
  })

  test('creates state/activity nodes and submits one draft batch', async ({ page }) => {
    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-toolbar').getByText('编辑模式', { exact: true })).toBeVisible()

    const sourceState = await createAtomicState(page, 'Flow input state', 'fixture_ready', 'draft-state:draft-1')
    const targetState = await createAtomicState(page, 'Flow output state', 'fixture_done', 'draft-state:draft-3')
    const atomicActivity = await createAtomicActivity(page, 'Flow atomic activity', 'atomic_activity:draft-atomic-activity:draft-5')

    await expect(page.locator('.draft-change-list')).toContainText('Flow input state')
    await expect(page.locator('.draft-change-list')).toContainText('Flow output state')
    await expect(page.locator('.draft-change-list')).toContainText('Flow atomic activity')
    const [commitRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        request.method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    const payload = JSON.parse(commitRequest.postData() || '{}')
    expect(payload.allow_warnings).toBe(false)
    expect(payload.validate_after_apply).toBe(true)
    expect(payload.changes).toHaveLength(5)

    expect(payload.changes[0]).toMatchObject({
      client_id: 'draft-1',
      entity_type: 'state_node',
      operation: 'create',
      payload: {
        name: 'Flow input state',
        state_kind: 'atomic',
        feature_key: 'fixture_dim_ready__flow_input_state',
        target_value: 'true',
        metadata_json: {
          dimension_template_key: 'fixture_dim_ready',
          state_object_name: 'Flow input state',
        },
      },
    })
    expect(payload.changes[1]).toMatchObject({
      client_id: 'draft-2',
      entity_type: 'state_node',
      operation: 'create',
      payload: {
        name: 'Flow input state false',
        state_kind: 'atomic',
        feature_key: 'fixture_dim_ready__flow_input_state',
        target_value: 'false',
      },
    })
    expect(payload.changes[2]).toMatchObject({
      client_id: 'draft-3',
      entity_type: 'state_node',
      operation: 'create',
      payload: {
        name: 'Flow output state',
        state_kind: 'atomic',
        feature_key: 'fixture_dim_done__flow_output_state',
        target_value: 'true',
        metadata_json: {
          dimension_template_key: 'fixture_dim_done',
          state_object_name: 'Flow output state',
        },
      },
    })
    expect(payload.changes[3]).toMatchObject({
      client_id: 'draft-4',
      entity_type: 'state_node',
      operation: 'create',
      payload: {
        name: 'Flow output state false',
        state_kind: 'atomic',
        feature_key: 'fixture_dim_done__flow_output_state',
        target_value: 'false',
      },
    })
    expect(payload.changes[4]).toMatchObject({
      client_id: 'draft-5',
      entity_type: 'atomic_activity',
      operation: 'create',
      payload: {
        name: 'Flow atomic activity',
      },
    })
    await expect(page.getByTestId('network-editor-toolbar').getByText('预览模式', { exact: true })).toBeVisible()
    await expect(atomicActivity).toBeHidden()
  })

  test('creates nodes from the blank right-click menu and pans the canvas with left drag', async ({ page }) => {
    await page.getByTestId('network-editor-enter-edit').click()

    const longStateName = 'Right click state with readable wrapped label across node'
    const stateClick = await openBlankContextMenu(page, 260, 150)
    await stateClick.menu.locator('button').nth(0).click()
    await createStateFromOpenDrawer(page, longStateName, 'fixture_ready', 'aggregate')
    const stateNode = page.getByTestId('network-editor-state-node-draft-state:draft-1')
    await expect(stateNode).toBeVisible()
    await expect(stateNode.locator('.node-name')).toHaveText(longStateName)
    const stateNameMetrics = await stateNode.locator('.node-name').evaluate((element: HTMLElement) => {
      const style = window.getComputedStyle(element)
      return {
        clientHeight: element.clientHeight,
        clientWidth: element.clientWidth,
        scrollHeight: element.scrollHeight,
        scrollWidth: element.scrollWidth,
        textOverflow: style.textOverflow,
        whiteSpace: style.whiteSpace,
      }
    })
    expect(stateNameMetrics.whiteSpace).toBe('nowrap')
    expect(stateNameMetrics.textOverflow).toBe('ellipsis')
    expect(stateNameMetrics.scrollHeight).toBeLessThanOrEqual(stateNameMetrics.clientHeight + 4)
    expect(stateNameMetrics.scrollWidth).toBeGreaterThan(stateNameMetrics.clientWidth)
    await expect(stateNode).toHaveAttribute('title', new RegExp(longStateName))
    await leftHoldLocatorWithoutDrag(page, stateNode)

    await createAtomicActivity(
      page,
      'Toolbar atomic activity',
      'atomic_activity:draft-atomic-activity:draft-2',
    )

    const beforePan = await locatorClientRect(stateNode)
    await leftDragBlankCanvas(page, 420, 520, -420, 0)
    await expect(page.getByTestId('network-editor-blank-context-menu')).toHaveCount(0)
    const afterPan = await locatorClientRect(stateNode)
    expect(afterPan.x).toBeLessThan(beforePan.x - 180)

    const farClick = await openBlankContextMenu(page, 500, 460)
    await farClick.menu.locator('button').nth(0).click()
    await createStateFromOpenDrawer(page, 'Far right state', 'fixture_done', 'aggregate')
    const expandedCanvas = await page.getByTestId('network-editor-x6-canvas').evaluate((element: HTMLElement) => {
      const graph = element.querySelector('.x6-graph') as HTMLElement | null
      const graphRect = graph?.getBoundingClientRect()
      return {
        clientWidth: element.clientWidth,
        clientHeight: element.clientHeight,
        scrollWidth: element.scrollWidth,
        scrollHeight: element.scrollHeight,
        graphWidth: graphRect?.width || 0,
        graphHeight: graphRect?.height || 0,
      }
    })
    expect(Math.max(expandedCanvas.scrollWidth, expandedCanvas.graphWidth)).toBeGreaterThanOrEqual(expandedCanvas.clientWidth)
    expect(Math.max(expandedCanvas.scrollHeight, expandedCanvas.graphHeight)).toBeGreaterThanOrEqual(expandedCanvas.clientHeight)

    const [commitRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/machine-types/1/network-editor/commit') &&
        request.method() === 'POST',
      ),
      page.getByTestId('network-editor-submit-draft').click(),
    ])
    const payload = JSON.parse(commitRequest.postData() || '{}')
    const createdNames = payload.changes
      .filter((change: any) => change.operation === 'create')
      .map((change: any) => change.payload?.name)
    expect(createdNames).toEqual(expect.arrayContaining([
      longStateName,
      'Toolbar atomic activity',
      'Far right state',
    ]))
  })

  test('projects first child additions inside their parent containers immediately', async ({ page }) => {
    await page.getByTestId('network-editor-enter-edit').click()
    await collapsePropertiesPane(page)

    const parentState = await createAggregateState(page, 'Parent state package', 'draft-state:draft-1')
    await parentState.hover()
    await parentState.locator('[data-action="create"]').click()
    const stateDrawer = page.getByTestId('network-editor-state-drawer')
    await expect(stateDrawer).toBeVisible()
    await stateDrawer.locator('.el-form-item').nth(1).locator('input').fill('First child state')
    await chooseElSelectOption(page, stateDrawer.getByTestId('network-editor-state-feature'), templateFeatureKey('fixture_ready'))
    await chooseElSelectOption(page, stateDrawer.getByTestId('network-editor-state-target-value'), 'true')
    await stateDrawer.getByTestId('network-editor-state-drawer-save').click()

    await expect(page.locator('.el-loading-mask')).toBeHidden({ timeout: 10000 })
    const stateContainer = page.getByTestId('network-editor-state-package-container-draft-state:draft-1')
    const childState = page.locator(
      '.x6-state-node[title*="state_node:draft-state:draft-2:draft-ref:draft-3"]',
    )
    await expect(stateContainer).toBeVisible()
    await expect(childState).toBeVisible()
    await expectLocatorInside(stateContainer, childState)

  })
})
