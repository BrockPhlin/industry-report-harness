import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { Type } from "typebox";

const execute = promisify(execFile);

export default function registerEvidence(pi) {
  pi.registerTool({
    name: "search_evidence",
    label: "检索光伏证据",
    description: "按指标编号查找只读光伏证据及其官方出处。",
    parameters: Type.Object({
      key: Type.Union([
        Type.Literal("pv-module-output"),
        Type.Literal("pv-module-price"),
        Type.Literal("pv-new-capacity"),
      ]),
    }),
    async execute(_id, params, signal) {
      const { stdout } = await execute(process.env.G11_PYTHON, [
        process.env.G11_PV_CLI, "evidence", "--", params.key,
      ], { signal, timeout: 5000, maxBuffer: 64 * 1024 });
      return { content: [{ type: "text", text: stdout }], details: JSON.parse(stdout) };
    },
  });
}
