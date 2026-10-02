// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 查看运营操作审计 GET /api/operations/audit */
export async function listOperatorAudit(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listOperatorAuditParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PageViewOperatorAuditView_>(
    "/api/operations/audit",
    {
      method: "GET",
      params: {
        // limit has a default value: 50
        limit: "50",
        ...params,
      },
      ...(options || {}),
    },
  );
}

/** 按目的地实际证据人工核对未知运营投递 POST /api/operations/audit/${param0}/resolve-delivery */
export async function resolveOperatorDelivery(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.resolveOperatorDeliveryParams,
  body: HotKeyAPI.AuditResolutionInput,
  options?: import("@/request").RequestOptions,
) {
  const { audit_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.OperatorAuditView>(
    `/api/operations/audit/${param0}/resolve-delivery`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      params: { ...queryParams },
      data: body,
      ...(options || {}),
    },
  );
}

/** 按账本政策版本修改预算 PUT /api/operations/budgets */
export async function updateOperatorBudget(
  body: HotKeyAPI.BudgetUpdateInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.BudgetPolicyView>("/api/operations/budgets", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** 读取当前词典版本 GET /api/operations/dictionaries */
export async function listOperatorDictionaries(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.DictionaryView[]>("/api/operations/dictionaries", {
    method: "GET",
    ...(options || {}),
  });
}

/** 保存可复验的词典新版本 PUT /api/operations/dictionaries */
export async function saveOperatorDictionary(
  body: HotKeyAPI.DictionaryInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.DictionaryView>("/api/operations/dictionaries", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** 运营分页查看反馈 GET /api/operations/feedback */
export async function listOperatorFeedback(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listOperatorFeedbackParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PageViewFeedbackView_>("/api/operations/feedback", {
    method: "GET",
    params: {
      // limit has a default value: 50
      limit: "50",
      ...params,
    },
    ...(options || {}),
  });
}

/** 读取运营私有反馈截图 GET /api/operations/feedback-attachments/${param0} */
export async function getOperatorFeedbackAttachment(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getOperatorFeedbackAttachmentParams,
  options?: import("@/request").RequestOptions,
) {
  const { attachment_id: param0, ...queryParams } = params;
  return request<{ id?: number }>(
    `/api/operations/feedback-attachments/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 运营处理、屏蔽或删除反馈 PATCH /api/operations/feedback/${param0} */
export async function updateOperatorFeedback(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.updateOperatorFeedbackParams,
  body: HotKeyAPI.FeedbackUpdateInput,
  options?: import("@/request").RequestOptions,
) {
  const { feedback_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.FeedbackUpdateView>(
    `/api/operations/feedback/${param0}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      params: { ...queryParams },
      data: body,
      ...(options || {}),
    },
  );
}

/** 读取实际进程、预算与失败状态 GET /api/operations/health */
export async function getOperationsHealth(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.OperationsHealthView>("/api/operations/health", {
    method: "GET",
    ...(options || {}),
  });
}

/** 读取实际维护计划与执行证据 GET /api/operations/maintenance */
export async function getOperatorMaintenance(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.MaintenanceStateView>(
    "/api/operations/maintenance",
    {
      method: "GET",
      ...(options || {}),
    },
  );
}

/** 接受有界维护任务 仅固定配置和备份ID;不允许请求提供库URL或文件路径。实际任务经原Job/Outbox与Worker执行。 POST /api/operations/maintenance */
export async function runOperatorMaintenance(
  body: HotKeyAPI.MaintenanceInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.MaintenanceAcceptedView>(
    "/api/operations/maintenance",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      data: body,
      ...(options || {}),
    },
  );
}

/** 分页读取通知账本与真实渠道回执 GET /api/operations/notification-deliveries */
export async function listOperatorNotificationDeliveries(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listOperatorNotificationDeliveriesParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PageViewNotificationDeliveryView_>(
    "/api/operations/notification-deliveries",
    {
      method: "GET",
      params: {
        // limit has a default value: 50
        limit: "50",
        ...params,
      },
      ...(options || {}),
    },
  );
}

/** 人工核对未知通知结果 同事务修订CAS、审计与原Job资格。确认未送达后仅允许显式重试原任务,不会立即重送。 POST /api/operations/notification-deliveries/${param0}/resolve */
export async function resolveOperatorNotificationDelivery(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.resolveOperatorNotificationDeliveryParams,
  body: HotKeyAPI.DeliveryResolutionInput,
  options?: import("@/request").RequestOptions,
) {
  const { delivery_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.NotificationDeliveryView>(
    `/api/operations/notification-deliveries/${param0}/resolve`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      params: { ...queryParams },
      data: body,
      ...(options || {}),
    },
  );
}

/** 读取通知目标与订阅 GET /api/operations/notification-targets */
export async function listOperatorNotificationTargets(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.TargetView[]>(
    "/api/operations/notification-targets",
    {
      method: "GET",
      ...(options || {}),
    },
  );
}

/** 配置通知目标与四类订阅 独立运营授权和CSRF;修订CAS与操作幂等。默认停用;启用时间重新计时防历史回发。凭据仅环境配置。 PUT /api/operations/notification-targets */
export async function saveOperatorNotificationTarget(
  body: HotKeyAPI.TargetSaveInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.TargetView>("/api/operations/notification-targets", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** 列出可核对的模型评测运行 GET /api/operations/selectbench */
export async function listOperatorSelectBench(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.SelectBenchRunView[]>(
    "/api/operations/selectbench",
    {
      method: "GET",
      ...(options || {}),
    },
  );
}

/** 导入同批黄金集并复算评测指标 POST /api/operations/selectbench */
export async function importOperatorSelectBench(
  body: HotKeyAPI.SelectBenchImportInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.SelectBenchRunView>("/api/operations/selectbench", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** 以生产关系提示词排队固定报道对评测 POST /api/operations/selectbench-relation-runs */
export async function runOperatorRelationBench(
  body: HotKeyAPI.RelationBenchGoldInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.SelectBenchAcceptedView>(
    "/api/operations/selectbench-relation-runs",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      data: body,
      ...(options || {}),
    },
  );
}

/** 导入同批报道对与各模型关系预测并复算指标 POST /api/operations/selectbench-relations */
export async function importOperatorRelationBench(
  body: HotKeyAPI.RelationBenchImportInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.SelectBenchRunView>(
    "/api/operations/selectbench-relations",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      data: body,
      ...(options || {}),
    },
  );
}

/** 以生产筛选链路排队黄金集模型评测 运营写权限;开关默认关闭。固定分组与seed抽样,每case/model原Job,生产预筛及两次独立评分,统一预算与未知响应不重付。 POST /api/operations/selectbench-runs */
export async function runOperatorSelectBench(
  body: HotKeyAPI.SelectBenchGoldInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.SelectBenchAcceptedView>(
    "/api/operations/selectbench-runs",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      data: body,
      ...(options || {}),
    },
  );
}

/** 按误判、分层或模型分歧逐条对比 GET /api/operations/selectbench/${param0} */
export async function getOperatorSelectBench(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getOperatorSelectBenchParams,
  options?: import("@/request").RequestOptions,
) {
  const { run_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.SelectBenchCasesView>(
    `/api/operations/selectbench/${param0}`,
    {
      method: "GET",
      params: {
        // limit has a default value: 100
        limit: "100",
        ...queryParams,
      },
      ...(options || {}),
    },
  );
}

/** 逐条比较关系误判、错误和模型分歧 GET /api/operations/selectbench/${param0}/relations */
export async function getOperatorRelationBench(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getOperatorRelationBenchParams,
  options?: import("@/request").RequestOptions,
) {
  const { run_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.RelationBenchCasesView>(
    `/api/operations/selectbench/${param0}/relations`,
    {
      method: "GET",
      params: {
        // limit has a default value: 100
        limit: "100",

        ...queryParams,
      },
      ...(options || {}),
    },
  );
}
