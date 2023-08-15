
function testProcessStockData() {
  var testJsonData = {
    "2914.T": [
      {"date": "2023-08-09", "open": 3104, "high": 3106, "low": 3093, "close": 3097},
      {"date": "2023-08-10", "open": 3098, "high": 3118, "low": 3094, "close": 3110},
      {"date": "2023-08-14", "open": 3115, "high": 3124, "low": 3110, "close": 3115}
    ]
  };
  
  processStockData(testJsonData);
  updateListSheet(testJsonData);
}

function logError(errorMessage) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var logSheet = ss.getSheetByName('log');
  if (!logSheet) {
    logSheet = ss.insertSheet('log');
    logSheet.appendRow(['Timestamp', 'Error Message']);
  }
  var timestamp = new Date();
  logSheet.appendRow([timestamp, errorMessage]);
}


// activeなシートの株価情報を全部削除する
function clearStockPriceData() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var sheetName = sheet.getName();
  var lastRow = sheet.getLastRow();

  // ダイアログで確認
  var ui = SpreadsheetApp.getUi();
  var response = ui.alert('シート ' + sheetName + ' の株価情報を全て削除してもいいですか？', ui.ButtonSet.YES_NO);

  // YESが選択された場合のみ削除
  if (response == ui.Button.YES) {
    // ヘッダー行を除いて削除するため、2行目から最終行まで削除します
    if (lastRow > 1) {
      sheet.deleteRows(2, lastRow - 1);
      logError("Deleted stock price data from sheet: " + sheetName); // ログへの記録も追加できます
    }
  }
}



// 全ての銘柄シートの株価情報を削除する
function clearAllStockPriceData() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var { tickers, markets } = getTickersAndMarkets();

  for (var i = 0; i < tickers.length; i++) {
    var ticker = tickers[i][0];
    var market = markets[i][0];
    var sheetName = ticker + "." + market;
    var sheet = ss.getSheetByName(sheetName);
    if (sheet) {
      var lastRow = sheet.getLastRow();
      if (lastRow > 1) {
        sheet.deleteRows(2, lastRow - 1);
      }
    }
  }
  logError("Deleted all stock price data")
}



function clearLogSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var logSheet = ss.getSheetByName('log');
  if (logSheet) {
    logSheet.clear();
    logSheet.appendRow(['Timestamp', 'Error Message']);
  }
}