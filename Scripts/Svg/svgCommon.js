/*
  Copyright Timo Lappalainen, 2016

  Some helper functions for handling objects with svg:
    AddSvgContainer
    GetSvgSizeInfo
    GetSvgNodeBoxInfo
*/

var svgIndex=0;

//************************************************************************************
// Function add svg container (also called chart) to given container on html.
//
// Usage: AddSvgContainer(container,options)
//    container   - #<id> of container like <div id="DisplayContainer" class="svg"></div>
//                  Can be also 'body' , so it will add svg container at the end of body
//    options     - optional parameters. Define it as {ID:'MySvg',width:1000, className='MySvgClass'}
//                  Optional parameters are:
//      ID          - ID of this svg container. You can refer it with d3.select('#<ID>'). Default svg_container<index>
//      className   - className for this svg container. With this you can have different class in your .css. Default 'svg'.
//      width       - width in units for your container. Note that on svg we use float coordinates. So it is actually same
//                    what the width is. So you can have width=1000 and draw circle to 500,500 with radius 500. There is no 
//                    difference to have width=1 and draw circle 0.5,0.5 with radius 0.5. Well the stroke width will then
//                    change. This can be solved by use scaling.
//                    Default is 800.
//      height      - height of the svg container. See also GetSvgSizeInfo. Default is width.
//
function AddSvgContainer(container,options) {
  var def={ID:null
          ,className:'svg'
          ,width:null
          ,height:null
          }; 
  if (options==null) options=def;
  CombineDefaultsToObject(options,def);

  if ( options.ID==null ) {
    options.ID='svg'+container.replace("#","_")+svgIndex;
    svgIndex++;
  }
  options.width=DefaultNum(options.width,800);
  options.height=DefaultNum(options.height,options.width);
  var svg = d3.select(container)
        .append('svg:svg').attr('id', options.ID)
        .attr('viewBox', "0 0 " + options.width + " " + options.height)
        .attr('preserveAspectRatio', "xMinYMin meet")
        .attr('class', options.className);
  var defs = svg.append('defs');

  return svg;    
}

//************************************************************************************
// Function returns svg container actual size information viewBox and BoundingClientRect.
// As additional function calculates actual svg container width and height. If you define
// for class:
//   width:300px; height:440px;
// and then call
//   AddSvgContainer('container',500,500);
// viewBox width and height still says 500 x 500, but container will be drawn to whole 
// 300px x 440px area. So actual svg container witdh x height would be calculated to 500 x 733.33
function GetSvgSizeInfo(svg) {
      var viewBox = svg[0][0].getAttribute("viewBox").split(" "),
          size = viewBox.slice(2),
          width = size[0],
          height = size[1];
      var box = svg[0][0].getBoundingClientRect();
      var scale=Math.min(box.width/width,box.height/height);
      return {
        viewBox: viewBox,
        BoundingClientRect: box,
        width: box.width/scale,
        height: box.height/scale,
        center: {x:box.width/scale/2,y:box.height/scale/2}
      };
}
  
//************************************************************************************
// Function returns svg node bounding box infomation. This uses simply node getBBox and adds
// extra information like centerX, centerY, bottom, right and svgContainer.
// Function is usefull for aligning svg nodes by others. So e.g. you can have:  
//      var speedBox = new ValueBox('15,6 kn','Speed','SpeedBox');
//      var depthBox = new ValueBox('150,2 m','Depth','DepthBox');
//      speedBox.init(svgContainer,200,15,600);
//      depthBox.init(svgContainer,200,GetSvgNodeBoxInfo(speedBox.ID).bottom+5,600,speedBox.scale);
// which aligns depthBox below speedbox.
//
// Currently result is in node own transform. Would be nice to have parameter for destination transform.
// Note that to make above sample aligning work, I have untransformed groupbox on each component
// like ValueBox.
function GetSvgNodeBoxInfo(ID) {
  var val={svgContainer:null, x:0, y:0, width:0, height:0, centerX:0, centerY:0, bottom:0, right:0}

  try {
    var svg=d3.select("#"+ID);
//    var transformText = svg.attr("transform");
//    var translate = d3.transform(transformText).translate;
//    var scale = d3.transform(transformText).scale;
    var val=svg.node().getBBox(); //.transform.baseVal.consolidate(); //svg.node().getBoundingClientRect(); //getBBox();
    val.center={};
    val.center.x=(val.x+val.width)/2;
    val.center.y=(val.y+val.height)/2;
    val.right=val.x+val.width;
    val.bottom=val.y+val.height;
    val.svgContainer=svg.node().farthestViewportElement;
  }
  catch (e) {
  }    
  
  return val;
}

/* Some common routines, which could be on own .js
*/

//************************************************************************************
// Function combines default properties to object. This is useful for function optional parameters
// provided as object.
function CombineDefaultsToObject(object,def) {
  var result;
  
  if ( isObject(object) ) {
    result=object;
    for (var property in def) {
        if ( isObject(def[property]) && object.hasOwnProperty(property) ) {
          object[property]=CombineDefaultsToObject(object[property],def[property]);
        } else {
          if (!object.hasOwnProperty(property)) {
            object[property]=def[property];
          }
        }
    }
  } else {
    result=def;
  }
  
  return result;
}

//************************************************************************************
function isObject(obj) {
  return obj === Object(obj);
}

//************************************************************************************
function DefaultNum(val,def) {
  if ( val==null ) val=def;
  
  if ( isNaN(val) ) {
    val=def;
  } 
  
  return val;
}

//************************************************************************************
function CreateSafeID(ID) {
  ID=ID.replace("#","_");
  ID=ID.replace(" ","_");
  
  return ID;
}

//************************************************************************************
function SetElementPosition(element,reference,defval) {
  element.attr('x',CalculateElementXPos(element,reference.x,defval)+reference.dx);
  element.attr('y',CalculateElementYPos(element,reference.y,defval)+reference.dy);
}

//************************************************************************************
function CalculateElementXPos(element,reference,defval) {
  var val=0;
  
  try {
    var bbox=element.node().getBBox();
    var refArr = reference.split(":");
    var pos=refArr[0];
    var ref=(refArr.length>1?refArr[1]:defval);
    var refBox=(ref.indexOf('#')==0?d3.select(ref).node().getBBox():null);
    var xOffset=0;
    if (element[0][0].tagName.toLowerCase()=='text'){
      switch ( element.style("text-anchor") ) {
        case 'middle': xOffset=bbox.width/2; break;
        case 'end': xOffset=bbox.width; break;
      }
    }
    switch (pos) {
          case 'leftSide':
            if ( refBox!=null ) {
              val=refBox.x+bbox.width;
            } else {
              val=Number(ref)-bbox.width;
            }
            break;
          case 'rightSide':
            if ( refBox!=null ) {
              val=refBox.x+refBox.width;
            } else {
              val=Number(ref);
            }
            break;
          case 'left':
            if ( refBox!=null ) {
              val=refBox.x;
            } else {
              val=Number(ref);
            }
            break;
          case 'right':
            if ( refBox!=null ) {
              val=refBox.x+refBox.width-bbox.width;
            } else {
              val=Number(ref)-bbox.width;
            }
            break;
          case 'center':
            if ( refBox!=null ) {
              val=refBox.x+refBox.width/2-bbox.width/2;
            } else {
              val=Number(ref)-bbox.width/2;
            }
            break;
    }
    val+=xOffset;
  }
  catch (e) {}
  
  return val;
}

//************************************************************************************
function CalculateElementYPos(element,reference,defval) {
  var val=0;
  
  try {
    var bbox=element.node().getBBox();
    var yOffset=0;
    // Calculate offset for text elements
    if (element[0][0].tagName.toLowerCase()=='text') {
      var yref=element.attr('dy');
      element.attr('dy','0.9em'); // set top aligned
      var topbox=element.node().getBBox();
      yOffset=topbox.y-bbox.y;
      element.attr('dy',yref); // restore y ref
    }
    var refArr = reference.split(":");
    var pos=refArr[0];
    var ref=(refArr.length>1?refArr[1]:defval);
    var refBox=(ref.indexOf('#')==0?d3.select(ref).node().getBBox():null);
    switch (pos) {
          case 'above':
            if ( refBox!=null ) {
              val=refBox.y-bbox.height;
            } else {
              val=Number(ref)-bbox.height;
            }
            break;
          case 'below':
            if ( refBox!=null ) {
              val=refBox.y+refBox.height;
            } else {
              val=Number(ref);
            }
            break;
          case 'top':
            if ( refBox!=null ) {
              val=refBox.y;
            } else {
              val=Number(ref);
            }
            break;
          case 'bottom':
            if ( refBox!=null ) {
              val=refBox.y+refBox.height-bbox.height;
            } else {
              val=Number(ref)-bbox.height;
            }
            break;
          case 'center':
            if ( refBox!=null ) {
              val=refBox.y+refBox.height/2-bbox.height/2;
            } else {
              val=Number(ref)-bbox.height/2;
            }
            break;
    }
    val+=yOffset;
  }
  catch (e) {}
  
  return val;
}

//************************************************************************************
function debug(msg) {
    setTimeout(function() {
        throw new Error(msg);
    }, 0);
}
