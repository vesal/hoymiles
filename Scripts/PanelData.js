

let PanelDataStr='{ "Power": 640.6, "MaxPower": 6480.0, "EnergyToday": 692, "EnergyTotal": 1570611, "PanelsData": [ { "Power": 39.8, "MaxPower": 405.0, "Location": { "x": 0, "y": 0 } }, { "Power": 44.4, "MaxPower": 405.0, "Location": { "x": 1, "y": 0 } }, { "Power": 52.7, "MaxPower": 405.0, "Location": { "x": 2, "y": 0 } }, { "Power": 53.7, "MaxPower": 405.0, "Location": { "x": 3, "y": 0 } }, { "Power": 41.9, "MaxPower": 405.0, "Location": { "x": 4, "y": 0 } }, { "Power": 38.8, "MaxPower": 405.0, "Location": { "x": 6, "y": 0 } }, { "Power": 38.0, "MaxPower": 405.0, "Location": { "x": 7, "y": 0 } }, { "Power": 38.1, "MaxPower": 405.0, "Location": { "x": 8, "y": 0 } }, { "Power": 39.8, "MaxPower": 405.0, "Location": { "x": 9, "y": 0 } }, { "Power": 39.0, "MaxPower": 405.0, "Location": { "x": 10, "y": 0 } }, { "Power": 39.1, "MaxPower": 405.0, "Location": { "x": 11, "y": 0 } }, { "Power": 35.1, "MaxPower": 405.0, "Location": { "x": 0, "y": 1 } }, { "Power": 31.6, "MaxPower": 405.0, "Location": { "x": 1, "y": 1 } }, { "Power": 35.1, "MaxPower": 405.0, "Location": { "x": 9, "y": 1 } }, { "Power": 36.2, "MaxPower": 405.0, "Location": { "x": 10, "y": 1 } }, { "Power": 37.3, "MaxPower": 405.0, "Location": { "x": 11, "y": 1 } } ], "Temperatures": [ 12.7, 13.3, 13.5, 15.3 ] }';
let PanelData=null;
let svgContainer=null;
let boxMain=null;

let PanelWidth=140;
let PanelHeight=70;
let PanelXCap=5;
let PanelYCap=1;
let MaxY=0;

// ************************************************************************************
function GetElem(_elem) {
  var elem=_elem;
  if ( _elem!=null && typeof(_elem)=="string" ) elem=document.getElementById(_elem);
  return elem;
}

// ************************************************************************************
function ShowElement(_elem,show=true) { 
  var elem=GetElem(_elem);
  if ( document.body.contains(elem) ) { 
    if ( show ) { elem.style.display = ""; } else { elem.style.display = "none"; } 
  }
}
function HideElement(elem) { ShowElement(elem,false); }

// ************************************************************************************
function DrawPanel(x,y,scale=1) {
  let box=null;
  box = boxMain.append('g').attr("x",x).attr("y",y).attr("transform", "translate("+x+","+y+") scale("+scale+")");
  box.insert("rect","#Panel1").attr("id", "Panel1")
  .attr("x", 0)
  .attr("y", 0)
  .attr("width", PanelWidth)
  .attr("height", PanelHeight)
//  .attr('rx', this.innerFrameRounding).attr('ry', this.innerFrameRounding)
  .attr("class", "ValueBox");
}

// ************************************************************************************
function AddText(node,x,y,text) {
  let s={'class':"valueText",'useSavedPos':true,'xAlign':'middle','yAlign':'center','text':'NA'};
  s.text=text;

  let valueBox=node.append("text")
  .attr("x", x)
  .attr("y", y)
    .attr("text-anchor", "middle")
//    .attr('dy', '0.3em')
  .attr("class", s.class)
  ;
  let valueText=valueBox
    .append("tspan")
//      .attr("dy", '0.5em')
//    .attr("text-anchor", "end")
//      .attr("x",0)
    .text(s.text)
    ;
}

// ************************************************************************************
function AddTextBox(node,x,y,w,h,text,relativeFill=null) {
  let box=null;
  let scale=1;

  x+=1;
  y+=1;

  box = node.append('g').attr("x",x).attr("y",y).attr("transform", "translate("+x+","+y+") scale("+scale+")");
  box.insert("rect","#Panel1").attr("id", "Panel1")
  .attr("x", 0)
  .attr("y", 0)
  .attr("width", w)
  .attr("height", h)
//  .attr('rx', this.innerFrameRounding).attr('ry', this.innerFrameRounding)
  .attr("class", "ValueBox");

  if ( relativeFill!=null ) {
    box = node.append('g').attr("x",x).attr("y",y).attr("transform", "translate("+x+","+y+") scale("+scale+")");
    box.insert("rect","#Panel1").attr("id", "Panel1")
    .attr("x", 1)
    .attr("y", 1)
    .attr("width", w*relativeFill-2)
    .attr("height", h-2)
    .attr("class", "ValueBoxRelativeFill");
  }

  AddText(box,w/2,h/2,text);
}

// ************************************************************************************
function DrawPanelByJson(Panel) {
  let x=Panel.Location.x*(PanelWidth+PanelXCap)+1;
  let y=Panel.Location.y*(PanelHeight+PanelYCap)+1;
  let maxPower=405;
  let scale=1;

  if ( y> MaxY ) MaxY=y;

  let box=null;
  box = boxMain.append('g').attr("x",x).attr("y",y).attr("transform", "translate("+x+","+y+") scale("+scale+")");
  box.insert("rect","#Panel1").attr("id", "Panel1")
  .attr("x", 0)
  .attr("y", 0)
  .attr("width", PanelWidth)
  .attr("height", PanelHeight)
//  .attr('rx', this.innerFrameRounding).attr('ry', this.innerFrameRounding)
  .attr("class", "PanelFrame");

  if ( Panel.MaxPower!=null && Panel.MaxPower>0 ) {
    let relativePower=Panel.Power/Panel.MaxPower;
    if ( relativePower>1 ) relativePower=1;
    box = boxMain.append('g').attr("x",x).attr("y",y).attr("transform", "translate("+x+","+y+") scale("+scale+")");
    box.insert("rect","#Panel1").attr("id", "Panel1")
    .attr("x", 1)
    .attr("y", PanelHeight-PanelHeight*relativePower+1)
    .attr("width", PanelWidth-2)
    .attr("height", PanelHeight*relativePower-2)
    //  .attr('rx', this.innerFrameRounding).attr('ry', this.innerFrameRounding)
    .attr("class", "PanelRelativeValueFrame");
  }

  AddText(box,PanelWidth/2,PanelHeight/2,Panel.Power.toFixed(1)+' W');
  return;

  let s={'class':"valueText",'useSavedPos':true,'xAlign':'middle','yAlign':'center','text':'NA'};
  s.text=Panel.Power.toFixed(1);

  let valueBox=box.append("text")
  .attr("x", PanelWidth/2)
  .attr("y", PanelHeight/2)
    .attr("text-anchor", "middle")
//    .attr('dy', '0.3em')
  .attr("class", s.class)
  ;
  let valueText=valueBox
    .append("tspan")
//      .attr("dy", '0.5em')
//    .attr("text-anchor", "end")
//      .attr("x",0)
    .text(s.text)
    ;
}

// ************************************************************************************
function DrawInformation() {
  let relativePower=null;
  if ( PanelData.MaxPower!=null && PanelData.MaxPower>0 ) relativePower=PanelData.Power/PanelData.MaxPower;
  AddTextBox(boxMain,0,MaxY+PanelHeight+30,150,50,'Teho = '+PanelData.Power.toFixed(0)+' W',relativePower);
  AddTextBox(boxMain,180,MaxY+PanelHeight+30,200,50,'Energia = '+(PanelData.EnergyToday/1000).toFixed(3)+' kWh');
}

// ************************************************************************************
function InitSvg() {
  let svgOptions={ID:null
    ,className:'svg'
    ,width:1000
    ,height:1000
    }; 
  svgContainer=AddSvgContainer('#DisplayContainer',svgOptions);
  boxMain = svgContainer.append('g').attr('id', 'Panels').attr('class', "tPanel");
}

// ************************************************************************************
function DrawPanelData() {
  HideElement("LoadingInfo");
  ShowElement("DisplayContainer");
  InitSvg();
  for ( let i=0; i<PanelData.PanelsData.length; i++ ) {
    DrawPanelByJson(PanelData.PanelsData[i]);
  }
  DrawInformation();
}

// ************************************************************************************
function LoadPanelDataTest() {
  PanelData=JSON.parse(PanelDataStr);
  DrawPanelData();
}

// ****************************************************************************
function LoadPanelData() {
  HideElement("DisplayContainer");
  ShowElement("LoadingInfo");
  var xhr = new XMLHttpRequest();
  xhr.onreadystatechange = function() {
      if (xhr.readyState == 4 && xhr.status == 200) {
        PanelData=JSON.parse(xhr.responseText);
        DrawPanelData();
      }
  }
  xhr.open('GET', 'http://192.168.59.4:8001/GetPanelData');
  xhr.send();
}

