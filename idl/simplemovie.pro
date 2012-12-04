;; given an array "data" whose first column indexes time, second column indexes position,
;; fourth column indexes models, and a vector of time labels, and axis labels
;; make one or a few movies! The third column indexes which variable we're plotting.
;; 
;; time is a 1D array assumed to contain the "time", or redshift values 
;;    for the corresponding cubes in data, indexed by the 1st column.
;; labels is a 1D array of strings, one for each of the variables indexed by the 3rd column in DATA,
;;    which specify part of the filename produced by simpleMovie.
;; colors is a (# timesteps) by (# models) array.
;; styles is a 1D array with (# models) elements specifying the style for each line.
;; wrtXlog specifies which variables (column 3 of data) should be plotted in log space
;; name is the base name for all files/movies produced in this procedure
;; sv specifies how the movie will be produced:
;;    1: IDL's built-in MPG creator (NOT RECOMMENDED)
;;    2: print to screen, save PNG, compile PNG's w/ ffmpeg (not recommended if you're producing a lot of movies)
;;    3: print to z buffer, save PNG, compile w/ ffmpeg (encouraged)
;;    4: same as 3, but try to adjust parameters so that the video is playable on a low-res projector
;;;;; KEYWORD ARGUMENTS:
;; prev: at a given time step, plot the data from both this time step and previous ones (# of previous timesteps = taillength)
;; psym: just the regular IDL keyword PSYM (see e.g. the documentation for PLOT)
;; axislabels: a vector of strings for labelling the axes appropriate for each variable
;;    indexed by the 3rd column in DATA- defaults to labels if unspecified
;; taillength (see "prev" above)
;; plotContours - not yet implemented: at each time step plot contours instead of lots of points.
;; whichFrames - specify a subset of all time indices to use for movies/plots, e.g. [2,17,30]
;; texLabels - LaTeX-ified version of axislabels. Only used if svSinglePlot == 2 (meaning save plots as .eps)
;; horizontal - for multi-paned plots, arrange them horizontally, as opposed to vertically
;; timeText - a string to be printed in front of time[i] at each timestep i.
;; NIndVarBins - when plotting many galaxies, this variable allows you to divide the galaxies into this many
;;   bins according to their value of the independent variable, such that equal numbers will appear in each bin.
;; percentileList - after dividing galaxies up into bins by their independent value, within each bin find 
;;   the value of each dependent variable at each percentile specified here. For instance the default plots 
;;   2-sigma contours+the median
;; svSinglePlot - the value of sv to use if we're producing a single plot. See figureinit.pro; typically 4 is a good choice
;; strt: for each variable, specify whether we should draw a straight line along x=y

PRO simpleMovie,data,time,labels,colors,styles,wrtXlog,name,sv,prev=prev,psym=psym,axislabels=axislabels,taillength=taillength,plotContours=plotContours,whichFrames=whichFrames,texLabels=texLabels,horizontal=horizontal,timeText=timeText,NIndVarBins=NIndVarBins,percentileList=percentileList,svSingePlot=svSinglePlot,strt=strt
  lth=1
  chth=1
  IF(sv EQ 3 || sv EQ 4 || sv EQ 5) THEN cg=1 ELSE cg=0
  IF(sv EQ 1) THEN cs=1 ELSE cs=2.8
  IF(sv EQ 4) THEN BEGIN 
    cs=2.5
    chth=2
    lth=5
  ENDIF

  PRINT, "Starting to make the files of the form: ", name,"*"

  ;; exclude the first time step from setting the range.
  ranges= simpleranges(data[2:n_elements(time)-1,*,*,*],wrtxlog)
  
  IF(n_elements(horizontal) EQ 0) THEN horizontal = 0
  IF(horizontal GE 2 OR horizontal LT 0) THEN horizontal = 1
  IF(n_elements(axislabels) EQ 0) THEN axislabels=labels[*]
  IF(n_elements(prev) EQ 0) THEN prev=0
  IF(n_elements(taillength) EQ 0) THEN taillength=2
  IF(n_elements(saveFrames) EQ 0) THEN saveFrames=0
  IF(n_elements(whichFrames) EQ 0) THEN whichFrames = indgen(n_elements(time))
  IF(n_elements(texLabels) EQ 0) THEN texLabels = axisLabels
  IF(n_elements(timeText) EQ 0) THEN timeText="z = "
  IF(n_elements(NIndVarBins) EQ 0) THEN NIndVarBins=0
  IF(n_elements(percentileList) EQ 0) THEN percentileList=[.025,.5,.975]
  IF(n_elements(svSinglePlot) EQ 0) THEN svSinglePlot = 4
  IF(n_elements(strt) EQ 0) THEN strt = intarr(n_elements(labels))


  ;; loop over y-axis variables to be plotted (except the first one, which is just the independent var!)
  FOR k=1,n_elements(labels)-1 DO BEGIN    
    fn=name+"_"+labels[k]
    dn="movie_"+name+"_"+labels[k]
    set_plot,'x'
    IF(sv EQ 3 || sv EQ 4) THEN set_plot,'z'
    IF(cg NE 1) THEN WINDOW,1,XSIZE=1024,YSIZE=1024,RETAIN=2
    IF(sv EQ 3 || sv EQ 4) THEN cgDisplay,1024,1024
    IF(sv EQ 1) THEN mpeg_id=MPEG_OPEN([1024,1024],FILENAME=(fn+".mpg"))
    IF(sv EQ 2 || sv EQ 3 || sv EQ 4) THEN BEGIN
      FILE_MKDIR,dn
    ENDIF
    IF(sv EQ 5) THEN BEGIN
        wf = n_elements(whichFrames)
	IF (wf GT 10) THEN message,"You have requested an unreasonable number of frames for a single plot."
	;cs = .3
        figureInit,(fn+"_timeSeries"),svSinglePlot,1+horizontal,1+(1-horizontal)
	multiplot,[0,wf*horizontal+1,wf*(1-horizontal)+1,0,0]
	!p.noerase=0
    ENDIF

    symsize = cs* 2 / (alog10(n_elements(data[0,0,0,*]))+1)
    IF(NIndVarBins GT 0) THEN symsize = symsize/3.0

    ;; counter of frames.
    count=0 
    ; length of a tail to put on each point which represents a galaxy when prev=1
    ; tailLength = fix(3.0/(float(n_elements(styles))/928.0)^(.25)) 

    ;; loop over time: each iteration of this loop will save a frame in a movie
    FOR tii=0,n_elements(whichFrames)-1 DO BEGIN  
      IF(sv EQ 5 and tii NE 0) THEN !p.noerase=1
      ti = whichFrames[tii]
      count=count+1
      SETCT,1,n_elements(styles),2

      ;; If this variable k is included in strt, draw a dashed line y=x.
      ;; Either way, this long statement draws the first plot for this frame.
      ;; Everything else will be overplotted on top in a few lines. 
      xt = axisLabels[0]
      IF(sv EQ 5 AND tii NE n_elements(whichFrames)-1 AND horizontal EQ 0) THEN xt=""
      yt = axisLabels[k]
      IF(sv EQ 5 AND tii NE 0 AND horizontal EQ 1) THEN yt=""
      ;IF(sv EQ 5) THEN yt=yt+" at z="+str(time)
      IF(strt[k] EQ 0) THEN $
        PLOT,[0],[0],COLOR=0,BACKGROUND=255,XSTYLE=1,YSTYLE=1,XTITLE=xt, $
         YTITLE=axislabels[k], XRANGE=ranges[*,0],YRANGE=ranges[*,k],ylog=wrtXlog[k], $
         xlog=wrtXlog[0],CHARTHICK=chth,CHARSIZE=cs,THICK=lth,XTHICK=lth,YTHICK=lth $
       ELSE $
        PLOT,findgen(1001)*(ranges[1,0]-ranges[0,0])/1000 + ranges[0,0], $
	 findgen(1001)*(ranges[1,0]-ranges[0,0])/1000 + ranges[0,0], $
         COLOR=0,BACKGROUND=255,XSTYLE=1,YSTYLE=1,XTITLE=xt, $
         YTITLE=axislabels[k],XRANGE=ranges[*,0],YRANGE=ranges[*,k],ylog=wrtXlog[k], $
         xlog=wrtXlog[0],linestyle=2,CHARSIZE=cs,CHARTHICK=chth,THICK=lth,XTHICK=lth,YTHICK=lth
      ;; that was all one line! It's now over, and our plotting space is set up.

      ;; Print the time in the upper left of the screen
      
      theTimeText = timeText+string(time[ti],Format='(D0.3)')

      IF(sv NE 5) THEN XYOUTS,.3,.87,theTimeText,/NORMAL,COLOR=0,CHARSIZE=cs,CHARTHICK=chth ; $
;      ELSE IF(horizontal EQ 0) THEN XYOUTS,.3,.95-float(tii)*(1.0 - 2.0/8.89)/(float(n_elements(whichFrames))),theTimeText,/NORMAL,COLOR=0,CHARSIZE=cs,CHARTHICK=chth $
;      ELSE XYOUTS,.1+float(tii)/float(n_elements(whichFrames)),.7,theTimeText,/NORMAL,COLOR=0,CHARSIZE=cs,CHARTHICK=chth

      ;; loop over models (4th column of data)
      FOR j=0,n_elements(data[0,0,0,*])-1 DO BEGIN 

        ;; Set the color table.	
;        IF(n_elements(styles) GT 80) THEN IF(sv NE 3 AND sv NE 4) THEN setct,5,n_elements(styles),j ELSE setct,3,n_elements(styles),0
	setct,1,n_elements(styles),j
        
        ;; Overplot the data for this model. If prev is set, draw a tail to include previous values of the data.
        OPLOT, data[ti,*,0,j], data[ti,*,k,j], COLOR=colors[ti,j],linestyle=styles[j],PSYM=psym,SYMSIZE=symsize,THICK=lth
        IF(prev EQ 1) THEN BEGIN
          OPLOT,data[MAX([0,ti-tailLength]):ti,0,0,j],data[MAX([0,ti-tailLength]):ti,0,k,j], COLOR=colors[ti,j],linestyle=0,THICK=1
        ENDIF
      ENDFOR ;; end loop over models

      ;; All of the models have been plotted. Now if the user has requested it, we would like to 
      ;; bin the data by its independent variable, and then its dependent variable!
      IF(NIndVarBins GT 0) THEN BEGIN
          ;;;; ASSUMING that there are some galaxies in each color bin,
          ncolors = MAX(colors)+1
          theCurves = dblarr(NIndVarBins, n_elements(percentileList), ncolors)
          ;; each color gets its own percentile curves
          FOR aColor=0, ncolors-1 DO BEGIN
              subset = WHERE(aColor EQ colors[ti,*], NInThisSubset)
              binCenters = dblarr(NIndVarBins)
              IF(NInThisSubset GT 0) THEN BEGIN
                  FOR indVarIndex=0, NIndVarBins-1 DO BEGIN
                      ;; 
                      thisIndBin = GetIthBin(indVarIndex, data[ti,0,0,*], NIndVarBins, subset=subset)
                      IF(wrtXlog[0] EQ 1 ) THEN binCenters[indVarIndex] = 10.0^avg(alog10((data[ti,0,0,subset])[thisIndBin]))$
                        ELSE binCenters[indVarIndex] = avg((data[ti,0,0,subset])[thisIndBin])
                      
                      ;dependentData = sort((data[ti,0,k,subset])[thisIndBin])
                      ;FOR percentileIndex=0, n_elements(percentileList)-1 DO BEGIN
                      ;    ;stop
                      ;    theCurves[indVarIndex, percentileIndex, aColor] = ((data[ti,0,k,subset])[thisIndBin])[dependentData[fix(percentileList[percentileIndex]*n_elements(dependentData))]]
                      ;ENDFOR ; end loop over percentiles
		  theCurves[indVarIndex, *, aColor] = percentiles((data[ti,0,k,subset])[thisIndBin],percentileList,wrtXlog[k])

                  ENDFOR ; end loop over independent variable bins.
		  ;stop
                  FOR percentileIndex=0,n_elements(percentiles)-1 DO OPLOT, binCenters, theCurves[*,percentileIndex,aColor], COLOR=aColor,THICK=2
              ENDIF ; end check that there are models w/ this color
          ENDFOR ; end loop over color
      ENDIF


      ;; We've created a single frame. What do we do with it?
      IF(sv EQ 1) THEN MPEG_PUT,mpeg_id,WINDOW=1,FRAME=count,/ORDER
      IF(sv EQ 2) THEN WRITE_PNG, dn+'/frame_'+string(count,FORMAT="(I4.4)") + '.png',TVRD(TRUE=1)
      IF(sv EQ 3 || sv EQ 4) THEN dummy=cgSnapshot(filename=(dn+'/frame_'+STRING(count-1,FORMAT="(I4.4)")),/png,/true,/nodialog) 
      IF(sv EQ 0) THEN wait,.05
      IF(sv EQ 5 AND tii NE n_elements(whichFrames)-1) THEN multiplot
    ENDFOR ;; end loop over time indices
    IF(sv EQ 1) THEN MPEG_SAVE,mpeg_id
    IF(sv EQ 1) THEN MPEG_CLOSE,mpeg_id
    ;IF(sv EQ 2 || sv EQ 3 || sv EQ 4) THEN spawn,("rm " + fn+".mpg") 
    ;IF(sv EQ 2 || sv EQ 3 || sv EQ 4) THEN spawn,("ffmpeg -f image2 -qscale 4 -i "+dn+"/frame_%04d.png " + fn + ".mpg")
    ;IF(sv EQ 2 || sv EQ 3 || sv EQ 4) THEN IF(saveFrames EQ 0) THEN spawn,("rm -rf "+dn)
    IF(sv EQ 5) THEN BEGIN
	figureClean,(fn+"_timeSeries"),svSinglePlot
        if(svSinglePlot EQ 2) THEN latexify,(fn+"_timeSeries.eps"),[axisLabels[0],axisLabels[k]],[texLabels[0],texLabels[k]],[.6,.6],height=8.89*(2-horizontal),width=8.89*(1+horizontal)
        multiplot,/default
    ENDIF
    set_plot,'x'
  ENDFOR ;; end loop over dependent variables
  IF(sv EQ 2|| sv EQ 3 || sv EQ 4) THEN spawn,"python makeGidgetMovies.py"
END

