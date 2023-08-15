
// 銘柄シートを作成する
function createStockSheets() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
var { tickers, markets } = getTickersAndMarkets();

  for (var i = 0; i < tickers.length; i++) {
    var ticker = tickers[i][0];
    var market = markets[i][0];
    var sheetName = ticker + "." + market;

    var targetSheet = ss.getSheetByName(sheetName);
    if (!targetSheet) {
      targetSheet = ss.insertSheet(sheetName);
      var headers = ["年月日", "始値(open)", "高値(high)", "低値(low)", "終値(close)"];
      targetSheet.getRange(1, 1, 1, headers.length).setValues([headers]);
      logError("created sheet : " + sheetName);
    }
    else {
      logError("found sheet : " + sheetName);
    }
  }
}

// 銘柄シートを全て削除する
function deleteStockSheets() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var { tickers, markets } = getTickersAndMarkets();

  for (var i = 0; i < tickers.length; i++) {
    var ticker = tickers[i][0];
    var market = markets[i][0];
    var sheetName = ticker + "." + market;

    var targetSheet = ss.getSheetByName(sheetName);
    if (targetSheet) {
      ss.deleteSheet(targetSheet);
      logError("deleted sheet : " + sheetName);
    }
  }
}

// 銘柄と市場の一覧を取得する関数
function getTickersAndMarkets() {
  var listSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('list');
  var tickers = listSheet.getRange('A2:A' + listSheet.getLastRow()).getValues();
  var markets = listSheet.getRange('B2:B' + listSheet.getLastRow()).getValues();
  return { tickers: tickers, markets: markets };
}

