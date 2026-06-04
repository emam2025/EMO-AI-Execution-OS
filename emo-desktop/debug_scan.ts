import { scanForPlaintextKeys } from "./lib/security/keychain-validator";
const findings = scanForPlaintextKeys("/Users/AI Workspace/Emo-AI/emo-desktop");
console.log("Total:", findings.length);
findings.forEach(f => {
  const rel = f.file.replace("/Users/AI Workspace/Emo-AI/emo-desktop/", "");
  console.log(`  ${rel}:${f.line} -> ${f.snippet.slice(0,80)}`);
});
