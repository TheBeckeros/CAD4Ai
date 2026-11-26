/** Which model the pane shows. */
export type Model = { path: string; name: string; mtimeMs: number; size: number }

/** Camera of the pane: angles in degrees, zoom as a factor. */
export type View = { yaw: number; pitch: number; zoom: number }

declare module 'claude-code' {
  interface PluginState {
    'CAD4Ai': {
      model: Shaped<Model | null>
      view: Shaped<View>
    }
  }
}
