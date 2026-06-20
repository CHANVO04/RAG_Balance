async function responseError(response: Response, fallback: string) {
  const text = await response.text()
  if (!text) return `${fallback} (HTTP ${response.status})`

  try {
    const payload = JSON.parse(text)
    const detail = payload?.detail ?? payload?.message ?? payload?.error
    if (typeof detail === 'string') return `${detail} (HTTP ${response.status})`
  } catch {
    return `${text} (HTTP ${response.status})`
  }

  return `${fallback} (HTTP ${response.status})`
}

export interface WorkspacePayload {
  id: string
  name: string
  icon: string
  collectionName: string
  systemPrompt: string
  createdAt: string
  strategy?: 'hybrid' | 'only_vector_fast' | 'only_vector_multimodal'
  isSetupComplete?: boolean
}

export async function createWorkspaceRemote(workspace: WorkspacePayload) {
  const response = await fetch('/api/workspaces', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(workspace),
  })
  if (!response.ok) {
    throw new Error(await responseError(response, 'Workspace create failed'))
  }
  return response.json()
}

export async function updateWorkspaceRemote(workspaceId: string, workspace: WorkspacePayload) {
  const response = await fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(workspace),
  })
  if (!response.ok) {
    throw new Error(await responseError(response, 'Workspace update failed'))
  }
  return response.json()
}

export async function deleteWorkspaceRemote(workspaceId: string) {
  const response = await fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(await responseError(response, 'Workspace delete failed'))
  }
  return response.json()
}
