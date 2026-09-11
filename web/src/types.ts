export type Rect = [number, number, number, number];
export type Anchor = {
  sha256: string;
  page: number;
  kind: "text" | "region" | "page";
  rects: Rect[];
  quote: string;
};
export type Paper = {
  id: string;
  title: string;
  sha256: string;
  page_count: number;
  current_page: number;
  source: Record<string, unknown>;
};
export type Thread = { id: string; title: string };
export type Context = {
  sources: { page: number; text: string; reason: string; truncated: boolean }[];
  characters: number;
  history_messages: number;
  scope: string;
  image_attached: boolean;
  anchor: Anchor | null;
};
export type Message = {
  id: string;
  role: string;
  content: string;
  status: string;
  model: string | null;
  anchor: Anchor | null;
  context: Context | null;
};
export type Note = {
  id: string;
  content: string;
  message_id: string | null;
  anchor: Anchor | null;
};
export type Provider = {
  provider: string;
  base_url: string;
  model: string;
  supports_images: boolean;
  effort: string;
  max_tokens: number;
};
export type Status = {
  configured: boolean;
  data_dir: string | null;
  key_configured: boolean;
  key_storage: "keychain" | "environment" | "none" | "unavailable";
  token: string;
  poppler_ready: boolean;
  provider: Provider;
};
export type Run = {
  id: string;
  status: string;
  error: string | null;
  usage:
    | {
        phase: string;
        model: string;
        tokens: Record<string, number> | null;
        finish_reason: string;
      }[]
    | null;
};
export type Candidate = {
  arxiv_id: string;
  title: string;
  authors: string[];
  year: string;
  url: string;
};
