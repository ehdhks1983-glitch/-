// lib/mcp/tools.ts  [신규 — P2 MCP 연동]
// AI 비서(ChatGPT·Claude 등)가 호출하는 도구. 게시(공개)는 하지 않는다 — 초안만 만들고
// 사장님이 편집 화면에서 검사 결과를 보고 승인해야 게시된다(P0 게시 전 승인 원칙 유지).

import type { SupabaseClient } from "@supabase/supabase-js";
import { analyzePrompt } from "@/lib/ai/analyzePrompt";
import { generateCopy } from "@/lib/ai/generateCopy";
import { selectTemplate } from "@/lib/ai/selectTemplate";
import { INDUSTRY_IDS, detectIndustry, getIndustry, isIndustryId } from "@/lib/compliance/industries";
import { checkCopy, checkText, hasBlocking } from "@/lib/compliance/check";
import { buildRulesFeed } from "@/lib/compliance/feed";
import { insertProject } from "@/lib/db/projects";
import { selectLeadStats, selectStats } from "@/lib/db/stats";
import { buildReport, lastDays, leadsSinceIso, totalsByProject } from "@/lib/analytics/report";
import { rateLimit } from "@/lib/rateLimit";

export interface ToolContext {
  /** 링크 생성용 사이트 주소(https://...) */
  origin: string;
  /** Bearer 토큰 소유자. 토큰이 없거나 틀리면 null */
  owner: string | null;
  /** service_role 클라이언트. 서버에 키가 없으면 null */
  admin: SupabaseClient | null;
}

export class ToolError extends Error {}

interface ToolDef {
  name: string;
  title: string;
  description: string;
  inputSchema: Record<string, unknown>;
  annotations: Record<string, boolean>;
  run: (args: Record<string, unknown>, ctx: ToolContext) => Promise<unknown>;
}

const DRAFTS_PER_HOUR = 10;
const MAX_DESCRIPTION = 2000;
const MAX_TEXT = 20_000;

const industryProp = {
  type: "string",
  enum: INDUSTRY_IDS,
  description: "업종 프리셋. general(일반)·food(식당·카페)·beauty(미용실)·academy(학원)·medical(병원)·health_food(건강기능식품)·cosmetics(화장품). 생략하면 내용으로 추정.",
};

function requireAuth(ctx: ToolContext): { owner: string; admin: SupabaseClient } {
  if (!ctx.admin) throw new ToolError("서버에 SUPABASE_SERVICE_ROLE_KEY 가 설정되지 않아 계정 도구를 쓸 수 없어요.");
  if (!ctx.owner) throw new ToolError("액세스 토큰이 필요해요. 대시보드 → 연동에서 토큰을 발급해 Authorization: Bearer 헤더로 보내 주세요.");
  return { owner: ctx.owner, admin: ctx.admin };
}

function str(v: unknown, max: number): string {
  return typeof v === "string" ? v.trim().slice(0, max) : "";
}

export const TOOLS: ToolDef[] = [
  {
    name: "check_ad_copy",
    title: "광고 문구 검사",
    description:
      "블로그 글·SNS 문구·상세페이지 문구가 한국 광고 규정(식품표시광고법·의료법·학원법·화장품법·공정위 지침 등)에 걸리는 표현을 포함하는지 업종 기준으로 검사합니다. block 은 쓰면 안 되는 표현, warn 은 근거 확인이 필요한 표현입니다. 법률 자문이 아닙니다.",
    inputSchema: {
      type: "object",
      properties: { text: { type: "string", description: "검사할 문구" }, industry: industryProp },
      required: ["text"],
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
    async run(args) {
      const text = str(args.text, MAX_TEXT);
      if (!text) throw new ToolError("text 를 입력해 주세요.");
      const industry = isIndustryId(args.industry) ? args.industry : "general";
      const findings = checkText(text, industry);
      return {
        industry: getIndustry(industry).name,
        can_publish: !hasBlocking(findings),
        findings: findings.map((f) => ({ severity: f.severity, match: f.match, message: f.message, basis: f.basis })),
      };
    },
  },
  {
    name: "get_compliance_rules",
    title: "광고 규정 규칙 조회",
    description: "업종 프리셋, 업종별 필수 표시 항목, 금칙어 규칙(정규식), AI 생성 표시 문구와 규칙 버전을 돌려줍니다.",
    inputSchema: { type: "object", properties: {} },
    annotations: { readOnlyHint: true, openWorldHint: false },
    async run() {
      return buildRulesFeed();
    },
  },
  {
    name: "list_pages",
    title: "내 페이지 목록",
    description: "내 랜딩페이지 목록과 게시 상태, 최근 7일 방문·신청 수, 공개 주소와 편집 주소를 돌려줍니다. 액세스 토큰이 필요합니다.",
    inputSchema: { type: "object", properties: {} },
    annotations: { readOnlyHint: true, openWorldHint: false },
    async run(_args, ctx) {
      const { owner, admin } = requireAuth(ctx);
      const { data, error } = await admin
        .from("projects")
        .select("id, title, slug, published, updated_at, compliance")
        .eq("owner", owner)
        .order("updated_at", { ascending: false });
      if (error) throw new Error(error.message);
      const rows = (data ?? []) as { id: string; title: string; slug: string; published: boolean; updated_at: string; compliance: { approved_at?: string } | null }[];
      const ids = rows.map((r) => r.id);
      const [stats, leads] = await Promise.all([
        selectStats(admin, ids, lastDays(7)[0]),
        selectLeadStats(admin, ids, leadsSinceIso(7)),
      ]);
      const totals = totalsByProject(stats, leads, 7);
      return rows.map((r) => ({
        id: r.id,
        title: r.title,
        status: r.published ? "게시중" : "비공개 초안",
        approved_at: r.compliance?.approved_at ?? null,
        views_7d: totals.get(r.id)?.views ?? 0,
        leads_7d: totals.get(r.id)?.leads ?? 0,
        public_url: r.published ? `${ctx.origin}/s/${r.slug}` : null,
        edit_url: `${ctx.origin}/project/${r.id}`,
      }));
    },
  },
  {
    name: "get_page_stats",
    title: "페이지 성과",
    description: "페이지 하나의 기간(7일 또는 30일) 방문·신청·전환율, 일별 추이, 유입 경로별 지표를 돌려줍니다. 액세스 토큰이 필요합니다.",
    inputSchema: {
      type: "object",
      properties: {
        page_id: { type: "string", description: "list_pages 의 id" },
        days: { type: "integer", enum: [7, 30], description: "기간(기본 30)" },
      },
      required: ["page_id"],
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
    async run(args, ctx) {
      const { owner, admin } = requireAuth(ctx);
      const pageId = str(args.page_id, 64);
      const days = args.days === 7 ? 7 : 30;
      const { data } = await admin.from("projects").select("id, title").eq("id", pageId).eq("owner", owner).maybeSingle();
      if (!data) throw new ToolError("페이지를 찾을 수 없어요. list_pages 로 id 를 확인해 주세요.");
      const [stats, leads] = await Promise.all([
        selectStats(admin, [pageId], lastDays(days)[0]),
        selectLeadStats(admin, [pageId], leadsSinceIso(days)),
      ]);
      const r = buildReport(stats, leads, days);
      return {
        title: data.title,
        period_days: days,
        views: r.views,
        leads: r.leads,
        conversion_percent: r.conversion,
        daily: r.daily,
        sources: r.sources.map((s) => ({ source: s.label, views: s.views, leads: s.leads, conversion_percent: s.conversion })),
      };
    },
  },
  {
    name: "create_draft_page",
    title: "랜딩페이지 초안 만들기",
    description:
      "사업 설명 한 줄로 랜딩페이지 문구를 생성해 비공개 초안으로 저장합니다. 공개 게시는 하지 않으며, 사장님이 edit_url 에서 광고 문구 검사 결과를 확인하고 승인해야 게시됩니다. 액세스 토큰이 필요합니다.",
    inputSchema: {
      type: "object",
      properties: {
        description: { type: "string", description: "무엇을 위한 페이지인지(사업·대상·원하는 행동)", maxLength: MAX_DESCRIPTION },
        industry: industryProp,
      },
      required: ["description"],
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
    async run(args, ctx) {
      const { owner, admin } = requireAuth(ctx);
      const description = str(args.description, MAX_DESCRIPTION);
      if (!description) throw new ToolError("description 을 입력해 주세요.");
      if (!rateLimit(`mcp-draft:${owner}`, DRAFTS_PER_HOUR, 3_600_000).ok) {
        throw new ToolError(`초안은 1시간에 ${DRAFTS_PER_HOUR}개까지 만들 수 있어요.`);
      }

      const analyzed = await analyzePrompt(description);
      const industry = isIndustryId(args.industry) ? args.industry : detectIndustry(analyzed);
      const biz = { ...analyzed, industry };
      const copy = await generateCopy(biz);
      const template = selectTemplate(biz);
      const project = await insertProject(admin, owner, {
        title: biz.service_name,
        prompt: description,
        template,
        biz_info: biz,
        copy,
        publish: false,
      });
      const findings = checkCopy(copy, industry);
      return {
        draft_id: project.id,
        status: "비공개 초안",
        edit_url: `${ctx.origin}/project/${project.id}`,
        industry: getIndustry(industry).name,
        headline: copy.hero.headline,
        needs_fix: hasBlocking(findings),
        findings: findings.map((f) => ({ severity: f.severity, where: f.fieldLabel, match: f.match, message: f.message })),
        next_step: "edit_url 에서 내용과 검사 결과를 확인하고 '게시하기 → 승인'을 눌러야 공개됩니다.",
      };
    },
  },
];
