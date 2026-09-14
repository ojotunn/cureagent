// Servidor do A MILLION KEYS. Serve a pasta site/ e nada mais.
// Sem dependencias de proposito: o build no Railway nao instala nada.

const http = require("http");
const fs = require("fs");
const path = require("path");

const RAIZ = path.join(__dirname, "site");
const PORTA = process.env.PORT || 8440;

const TIPOS = {
  ".html": "text/html; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".csv": "text/csv; charset=utf-8",
  ".pdb": "chemical/x-pdb",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
};

http.createServer((req, res) => {
  // so GET/HEAD: o site nao recebe nada de ninguem
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405, {"Allow": "GET, HEAD"});
    return res.end("method not allowed");
  }

  let caminho;
  try {
    caminho = decodeURIComponent(new URL(req.url, "http://x").pathname);
  } catch {
    res.writeHead(400);
    return res.end("bad request");
  }
  if (caminho === "/" || caminho === "") caminho = "/index.html";

  // nunca sair da pasta site/
  const alvo = path.join(RAIZ, path.normalize(caminho));
  if (!alvo.startsWith(RAIZ)) {
    res.writeHead(403);
    return res.end("forbidden");
  }

  fs.readFile(alvo, (err, dados) => {
    if (err) {
      res.writeHead(404, {"Content-Type": "text/plain; charset=utf-8"});
      return res.end("not found");
    }
    const ext = path.extname(alvo).toLowerCase();
    const cabecalhos = {
      "Content-Type": TIPOS[ext] || "application/octet-stream",
      "Content-Length": dados.length,
      // dados e pagina mudam a cada publicacao: nada de cache velho na tela
      "Cache-Control": ext === ".html" || ext === ".json"
        ? "no-store"
        : "public, max-age=3600",
      "X-Content-Type-Options": "nosniff",
    };
    if (ext === ".csv") {
      cabecalhos["Content-Disposition"] =
        `attachment; filename="${path.basename(alvo)}"`;
    }
    res.writeHead(200, cabecalhos);
    res.end(req.method === "HEAD" ? undefined : dados);
  });
}).listen(PORTA, () => {
  console.log(`A MILLION KEYS servindo em :${PORTA}`);
});
