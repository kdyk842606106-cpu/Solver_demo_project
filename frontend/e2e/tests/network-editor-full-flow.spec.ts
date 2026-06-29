import { test, expect } from '@playwright/test'

const machineTypes = [
  { id: 1, code: 'EDITOR_FLOW', name: 'Editor Flow Machine', description: 'Full editor flow fixture' },
]

const stateFeatureDefs = [
  {
    id: 1,
    machine_type_id: 1,
    feature_key: 'fixture_ready',
    feature_name: 'Fixture Ready',
    value_type: 'enum',
    allowed_values: ['false', 'true'],
  },
  {
    id: 2,
    machine_type_id: 1,
    feature_key: 'fixture_done',
    feature_name: 'Fixture Done',
    value_type: 'enum',
    allowed_values: ['false', 'true'],
  },
]

const emptyGraph = {
  machine_type_id: 1,
  revision: 'editor-full-flow-revision',
  view_mode: 'implementation',
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
    virtual_activity_count: 0,
    executable_activity_count: 0,
    edge_count: 0,
    coverage_gap_count: 0,
    partial_virtual_activity_count: 0,
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
  await expect(page.getByTestId('network-editor-canvas')).toBeVisible()
  await expect(page.getByTestId('network-editor-x6-canvas')).toBeVisible()
}

async function createAtomicState(page: any, name: string, featureKey: string, expectedDraftId: string) {
  await page.getByTestId('network-editor-create-state').click()
  const drawer = page.getByTestId('network-editor-state-drawer')
  await expect(drawer).toBeVisible()
  await drawer.locator('.el-form-item').nth(1).locator('input').fill(name)
  await chooseElSelectOption(page, drawer.getByTestId('network-editor-state-feature'), featureKey)
  await chooseElSelectOption(page, drawer.getByTestId('network-editor-state-target-value'), 'true')
  await drawer.getByTestId('network-editor-state-drawer-save').click()
  await expect(drawer).toBeHidden()
  const node = page.getByTestId(`network-editor-state-node-${expectedDraftId}`)
  await expect(node).toBeVisible()
  await expect(node).toContainText(name)
  return node
}

async function createAggregateState(page: any, name: string, expectedDraftId: string) {
  await page.getByTestId('network-editor-create-state').click()
  const drawer = page.getByTestId('network-editor-state-drawer')
  await expect(drawer).toBeVisible()
  await chooseStateKind(drawer, 'aggregate')
  await drawer.locator('.el-form-item').nth(1).locator('input').fill(name)
  await drawer.getByTestId('network-editor-state-drawer-save').click()
  await expect(drawer).toBeHidden()
  const node = page.getByTestId(`network-editor-state-node-${expectedDraftId}`)
  await expect(node).toBeVisible()
  await expect(node).toContainText(name)
  return node
}

async function createVirtualActivity(page: any, name: string, expectedDraftId: string) {
  await page.getByTestId('network-editor-create-activity').click()
  const drawer = page.getByTestId('network-editor-activity-drawer')
  await expect(drawer).toBeVisible()
  await drawer.locator('.el-form-item').nth(1).locator('input').fill(name)
  await drawer.getByTestId('network-editor-activity-drawer-save').click()
  await expect(drawer).toBeHidden()
  const node = page.getByTestId(`network-editor-activity-node-${expectedDraftId}`)
  await expect(node).toBeVisible()
  await expect(node).toContainText(name)
  return node
}

async function createAtomicActivity(page: any, name: string, expectedDraftId: string) {
  await page.getByTestId('network-editor-create-atomic').click()
  const drawer = page.getByTestId('network-editor-atomic-drawer')
  await expect(drawer).toBeVisible()
  await drawer.locator('.el-form-item').nth(1).locator('input').fill(name)
  await drawer.getByTestId('network-editor-atomic-drawer-save').click()
  await expect(drawer).toBeHidden()
  const node = page.getByTestId(`network-editor-activity-node-${expectedDraftId}`)
  await expect(node).toBeVisible()
  await expect(node).toContainText(name)
  return node
}

async function dragRightPortToLeftPort(page: any, sourceLocator: any, targetLocator: any) {
  const sourcePort = sourceLocator.locator('.semantic-port.port-right')
  const targetPort = targetLocator.locator('.semantic-port.port-left')
  await targetPort.scrollIntoViewIfNeeded()
  await sourcePort.scrollIntoViewIfNeeded()
  const sourceBox = await locatorClientRect(sourcePort, { preferOwnRect: true })
  const targetBox = await locatorClientRect(targetPort, { preferOwnRect: true })
  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2)
  await page.waitForTimeout(30)
  await page.mouse.down({ button: 'left' })
  await page.waitForTimeout(30)
  await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, { steps: 12 })
  await page.mouse.up({ button: 'left' })
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

  test('creates state/activity nodes, connects edges, and submits one draft batch', async ({ page }) => {
    await page.getByTestId('network-editor-enter-edit').click()
    await expect(page.getByTestId('network-editor-toolbar').getByText('编辑模式', { exact: true })).toBeVisible()

    const sourceState = await createAtomicState(page, 'Flow input state', 'fixture_ready', 'draft-state:draft-1')
    const targetState = await createAtomicState(page, 'Flow output state', 'fixture_done', 'draft-state:draft-2')
    const virtualActivity = await createVirtualActivity(page, 'Flow virtual activity', 'activity_node:draft-activity:draft-3')
    const atomicActivity = await createAtomicActivity(page, 'Flow atomic activity', 'atomic_activity:draft-atomic-activity:draft-4')

    await expect(page.locator('.draft-change-list')).toContainText('Flow input state')
    await expect(page.locator('.draft-change-list')).toContainText('Flow output state')
    await expect(page.locator('.draft-change-list')).toContainText('Flow virtual activity')
    await expect(page.locator('.draft-change-list')).toContainText('Flow atomic activity')

    await dragRightPortToLeftPort(page, sourceState, virtualActivity)
    await expect(page.locator('[data-cell-id^="pending-binding-preview"]')).toHaveCount(1)
    await confirmDroppedBinding(page)
    await expect(page.locator('[data-cell-id^="draft-binding"]')).toHaveCount(1)
    await expect(page.locator('.draft-change-list')).toContainText('context_input')

    await dragRightPortToLeftPort(page, virtualActivity, targetState)
    await expect(page.locator('[data-cell-id^="pending-binding-preview"]')).toHaveCount(1)
    await confirmDroppedBinding(page)
    await expect(page.locator('[data-cell-id^="draft-binding"]')).toHaveCount(2)
    await expect(page.locator('.draft-change-list')).toContainText('declared_output')

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
    expect(payload.changes).toHaveLength(6)

    expect(payload.changes[0]).toMatchObject({
      client_id: 'draft-1',
      entity_type: 'state_node',
      operation: 'create',
      payload: {
        name: 'Flow input state',
        state_kind: 'atomic',
        feature_key: 'fixture_ready',
        target_value: 'true',
      },
    })
    expect(payload.changes[1]).toMatchObject({
      client_id: 'draft-2',
      entity_type: 'state_node',
      operation: 'create',
      payload: {
        name: 'Flow output state',
        state_kind: 'atomic',
        feature_key: 'fixture_done',
        target_value: 'true',
      },
    })
    expect(payload.changes[2]).toMatchObject({
      client_id: 'draft-3',
      entity_type: 'activity_node',
      operation: 'create',
      payload: {
        name: 'Flow virtual activity',
        parent_id: null,
      },
    })
    expect(payload.changes[3]).toMatchObject({
      client_id: 'draft-4',
      entity_type: 'atomic_activity',
      operation: 'create',
      payload: {
        name: 'Flow atomic activity',
      },
    })
    expect(payload.changes[4]).toMatchObject({
      entity_type: 'activity_state_binding',
      operation: 'create',
      payload: {
        activity_node_id: { _draft_ref: 'draft-3' },
        state_node_id: { _draft_ref: 'draft-1' },
        binding_role: 'context_input',
      },
    })
    expect(payload.changes[5]).toMatchObject({
      entity_type: 'activity_state_binding',
      operation: 'create',
      payload: {
        activity_node_id: { _draft_ref: 'draft-3' },
        state_node_id: { _draft_ref: 'draft-2' },
        binding_role: 'declared_output',
      },
    })

    await expect(page.getByTestId('network-editor-toolbar').getByText('预览模式', { exact: true })).toBeVisible()
    await expect(atomicActivity).toBeHidden()
  })

  test('projects first child additions inside their parent containers immediately', async ({ page }) => {
    await page.getByTestId('network-editor-enter-edit').click()

    const parentState = await createAggregateState(page, 'Parent state package', 'draft-state:draft-1')
    await parentState.locator('[data-action="create"]').click()
    const stateDrawer = page.getByTestId('network-editor-state-drawer')
    await expect(stateDrawer).toBeVisible()
    await stateDrawer.locator('.el-form-item').nth(1).locator('input').fill('First child state')
    await chooseElSelectOption(page, stateDrawer.getByTestId('network-editor-state-feature'), 'fixture_ready')
    await chooseElSelectOption(page, stateDrawer.getByTestId('network-editor-state-target-value'), 'true')
    await stateDrawer.getByTestId('network-editor-state-drawer-save').click()

    const stateContainer = page.getByTestId('network-editor-state-package-container-draft-state:draft-1')
    const childState = page.getByTestId('network-editor-state-node-draft-state:draft-2')
    await expect(stateContainer).toBeVisible()
    await expect(childState).toBeVisible()
    await expectLocatorInside(stateContainer, childState)

    const parentActivity = await createVirtualActivity(page, 'Parent virtual activity', 'activity_node:draft-activity:draft-3')
    await parentActivity.locator('[data-action="create"]').click()
    const activityDrawer = page.getByTestId('network-editor-activity-drawer')
    await expect(activityDrawer).toBeVisible()
    await activityDrawer.locator('.el-form-item').nth(1).locator('input').fill('First child activity')
    await activityDrawer.getByTestId('network-editor-activity-drawer-save').click()

    const activityContainer = page.getByTestId('network-editor-virtual-activity-container-activity_node:draft-activity:draft-3')
    const childActivity = page.getByTestId('network-editor-activity-node-activity_node:draft-activity:draft-4')
    await expect(activityContainer).toBeVisible()
    await expect(childActivity).toBeVisible()
    await expectLocatorInside(activityContainer, childActivity)
  })
})
