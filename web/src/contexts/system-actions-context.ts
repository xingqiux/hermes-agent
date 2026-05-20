import { createContext } from "react";
import type { ActionStatusResponse, UpdateCheckResponse } from "@/lib/api";

export const SystemActionsContext = createContext<SystemActionsState | null>(
  null,
);

export type SystemAction = "restart";

export interface SystemActionsState {
  actionStatus: ActionStatusResponse | null;
  activeAction: SystemAction | null;
  checkUpdate: () => Promise<void>;
  dismissLog: () => void;
  isBusy: boolean;
  isRunning: boolean;
  pendingAction: SystemAction | null;
  runAction: (action: SystemAction) => Promise<void>;
  updateCheck: UpdateCheckResponse | null;
  updateCheckLoading: boolean;
}
