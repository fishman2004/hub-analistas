/**
 * Ponte do Hub dos Analistas: entrega a base "(DADOS) - 8081 - Vendas" do Google Drive
 * só para quem manda a chave certa (o Hub do PC da sala).
 *
 * Como usar (o passo a passo com prints está em docs/drive-8081.md):
 * 1. Com a conta Google que já abre o arquivo da 8081, crie um projeto em script.google.com
 *    e cole este código todo no lugar do que vier.
 * 2. Em Configurações do projeto (engrenagem) > Propriedades do script, crie:
 *      CHAVE_HUB   = a chave que o Hub gerou em Configurações > Base 8081 do Google Drive
 *      ARQUIVO_ID  = o id do arquivo (no link .../file/d/ID/view, o trecho entre /d/ e /view)
 *    Se a automação cria um arquivo novo a cada vez (o id muda), use no lugar do ARQUIVO_ID:
 *      PASTA_ID    = o id da pasta (no link .../folders/ID) e a ponte pega o arquivo
 *                    mais novo da pasta cujo nome começa com "(DADOS) - 8081"
 * 3. Implantar > Nova implantação > tipo "App da Web": Executar como "Eu" e
 *    Quem pode acessar "Qualquer pessoa". Autorize e copie o endereço que termina com /exec.
 *
 * Sem a chave, a ponte responde só {"ok": false, "erro": "chave"}: o arquivo não sai.
 * Não coloque a chave neste código nem no GitHub: ela fica só nas Propriedades do script.
 */

var NOME_DA_BASE = '(DADOS) - 8081';
var TIPOS = { csv: 'csv', xlsx: 'xlsx', xlsm: 'xlsm' };

function doGet(e) {
  var props = PropertiesService.getScriptProperties();
  var chave = props.getProperty('CHAVE_HUB') || '';
  var recebida = (e && e.parameter && e.parameter.chave) || '';
  if (chave.length < 32 || recebida !== chave) {
    return responder({ ok: false, erro: 'chave' });
  }
  try {
    var arquivo = acharArquivo(props);
    var modificado = arquivo.getLastUpdated().toISOString();
    if (e.parameter.desde === modificado) {
      return responder({ ok: true, igual: true, modificado: modificado });
    }
    var tipo, blob;
    if (arquivo.getMimeType() === MimeType.GOOGLE_SHEETS) {
      // planilha do Google: exporta a primeira aba como .xlsx
      var url = 'https://docs.google.com/spreadsheets/d/' + arquivo.getId() + '/export?format=xlsx';
      blob = UrlFetchApp.fetch(url, { headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() } }).getBlob();
      tipo = 'xlsx';
    } else {
      var partes = arquivo.getName().toLowerCase().split('.');
      tipo = TIPOS[partes[partes.length - 1]] || (arquivo.getMimeType() === MimeType.CSV ? 'csv' : '');
      if (!tipo) {
        return responder({ ok: false, erro: 'o arquivo não é .xlsx, .xlsm, .csv nem planilha do Google' });
      }
      blob = arquivo.getBlob();
    }
    return responder({ ok: true, modificado: modificado, tipo: tipo,
                       conteudo: Utilities.base64Encode(blob.getBytes()) });
  } catch (erro) {
    return responder({ ok: false, erro: String(erro && erro.message || erro).slice(0, 200) });
  }
}

function acharArquivo(props) {
  var id = props.getProperty('ARQUIVO_ID');
  if (id) {
    return DriveApp.getFileById(id);
  }
  var pasta = props.getProperty('PASTA_ID');
  if (!pasta) {
    throw new Error('falta ARQUIVO_ID ou PASTA_ID nas Propriedades do script');
  }
  var arquivos = DriveApp.getFolderById(pasta).getFiles();
  var melhor = null;
  while (arquivos.hasNext()) {
    var f = arquivos.next();
    if (f.getName().indexOf(NOME_DA_BASE) === 0 && !f.isTrashed() &&
        (melhor === null || f.getLastUpdated() > melhor.getLastUpdated())) {
      melhor = f;
    }
  }
  if (melhor === null) {
    throw new Error('nenhum arquivo começando com "' + NOME_DA_BASE + '" na pasta');
  }
  return melhor;
}

function responder(dados) {
  return ContentService.createTextOutput(JSON.stringify(dados)).setMimeType(ContentService.MimeType.JSON);
}
