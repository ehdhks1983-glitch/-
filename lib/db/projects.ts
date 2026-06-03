// lib/db/projects.ts  [신규] — 서버 전용 프로젝트 쿼리 헬퍼.
// 호출자가 createSupabaseServer()로 만든 클라이언트를 넘긴다(인증/RLS는 그 세션 기준).
// 주의: projects 에는 "게시물 공개 read" RLS 정책이 있어, 소유자 조회는 RLS만 믿지 말고
//       반드시 owner 를 명시적으로 필터한다(안 그러면 남의 게시물까지 섞여 나옴).

import type { SupabaseClient } from "@supabase/supabase-js";
import type { BizInfo, SectionCopy, TemplateId } from "@/lib/ai/types";

export interface ProjectRow {
  id: string;
  owner: string;
  slug: string;
  title: string;
  prompt: string;
  template: TemplateId;
  biz_info: BizInfo;
  copy: SectionCopy;
  published: boolean;
  created_at: string;
  updated_at: string;
}

export interface NewProject {
  title: string;
  prompt: string;
  template: TemplateId;
  biz_info: BizInfo;
  copy: SectionCopy;
  publish?: boolean;
}

export interface ProjectPatch {
  template?: TemplateId;
  copy?: SectionCopy;
  published?: boolean;
  title?: string;
}

/** 사람이 읽기 쉬운 + 충돌 적은 slug 생성(ASCII 영숫자 + 랜덤 접미). */
export function slugify(base: string): string {
  const ascii = base
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  const rand = Math.random().toString(36).slice(2, 7);
  return `${ascii || "page"}-${rand}`;
}

export async function insertProject(
  supabase: SupabaseClient,
  owner: string,
  input: NewProject,
): Promise<ProjectRow> {
  const title = input.title || input.biz_info.service_name || "제목 없는 페이지";
  const { data, error } = await supabase
    .from("projects")
    .insert({
      owner,
      slug: slugify(title),
      title,
      prompt: input.prompt,
      template: input.template,
      biz_info: input.biz_info,
      copy: input.copy,
      published: input.publish ?? true,
    })
    .select()
    .single();
  if (error) throw new Error(error.message);
  return data as ProjectRow;
}

/** 내 프로젝트 목록. owner 명시 필터(공개 read 정책과 섞이지 않도록). */
export async function selectMyProjects(supabase: SupabaseClient, ownerId: string): Promise<ProjectRow[]> {
  const { data, error } = await supabase
    .from("projects")
    .select("*")
    .eq("owner", ownerId)
    .order("created_at", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as ProjectRow[];
}

/** 공개 게시된 프로젝트를 slug로 조회(비로그인도 RLS 정책상 select 허용). */
export async function selectPublishedBySlug(
  supabase: SupabaseClient,
  slug: string,
): Promise<ProjectRow | null> {
  const { data, error } = await supabase
    .from("projects")
    .select("*")
    .eq("slug", slug)
    .eq("published", true)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return (data as ProjectRow) ?? null;
}

/** 내 단건 조회. owner 명시 필터 → 남의 게시물 조회 차단. */
export async function selectMyProjectById(
  supabase: SupabaseClient,
  id: string,
  ownerId: string,
): Promise<ProjectRow | null> {
  const { data, error } = await supabase
    .from("projects")
    .select("*")
    .eq("id", id)
    .eq("owner", ownerId)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return (data as ProjectRow) ?? null;
}

/** 내 프로젝트 수정. owner 불일치/없음이면 null 반환(라우트에서 404 처리). */
export async function updateProject(
  supabase: SupabaseClient,
  id: string,
  ownerId: string,
  patch: ProjectPatch,
): Promise<ProjectRow | null> {
  const { data, error } = await supabase
    .from("projects")
    .update({ ...patch, updated_at: new Date().toISOString() })
    .eq("id", id)
    .eq("owner", ownerId)
    .select()
    .maybeSingle();
  if (error) throw new Error(error.message);
  return (data as ProjectRow) ?? null;
}

export async function deleteProject(supabase: SupabaseClient, id: string, ownerId: string): Promise<void> {
  const { error } = await supabase.from("projects").delete().eq("id", id).eq("owner", ownerId);
  if (error) throw new Error(error.message);
}
