/* Pit Stack audio: one pre-rendered loop, one gain node, no animation timers. */
(function () {
  'use strict';
  const STORAGE='fastlap.pitStack.audio.v1';
  window.PitStackAudio=class {
    constructor(media,button,volume) {
      this.media=media;this.button=button;this.volumeControl=volume;
      this.enabled=true;this.volume=.22;this.active=false;this.blocked=false;
      this.context=null;this.gain=null;this.request=0;this.pending=false;
      try {
        const saved=JSON.parse(localStorage.getItem(STORAGE));
        if(typeof saved?.enabled==='boolean')this.enabled=saved.enabled;
        if(Number.isFinite(saved?.volume))this.volume=Math.max(0,Math.min(1,saved.volume));
      } catch { /* Private browsing / disabled storage must not block the game. */ }
      media.loop=true;media.preload='none';media.preservesPitch=true;
      button.addEventListener('click',()=>{
        button.focus({preventScroll:true});
        if(this.blocked && this.enabled)this.blocked=false;
        else this.enabled=!this.enabled;
        this.save();this.refresh();
      });
      volume.addEventListener('input',()=>{
        this.volume=Math.max(0,Math.min(1,Number(volume.value)/100));
        if(this.volume>0){this.enabled=true;this.blocked=false;}
        this.save();this.refresh();
      });
      this.render();
    }
    save() {
      try {localStorage.setItem(STORAGE,JSON.stringify({enabled:this.enabled,volume:this.volume}));} catch {}
    }
    render() {
      const audible=this.enabled && this.volume>0;
      this.button.setAttribute('aria-pressed',String(audible));
      this.button.setAttribute('aria-label',this.blocked?'Повторить включение музыки':audible?'Выключить музыку':'Включить музыку');
      this.button.title=this.blocked?'Нажми, чтобы повторить включение музыки':audible?'Музыка включена':'Музыка выключена';
      this.button.classList.toggle('is-muted',!audible || this.blocked);
      this.volumeControl.value=Math.round(this.volume*100);
      this.volumeControl.setAttribute('aria-valuetext',Math.round(this.volume*100)+'%');
    }
    graph() {
      const Context=window.AudioContext || window.webkitAudioContext;
      if(this.context || !Context)return;
      try {
        const context=new Context(),gain=context.createGain();
        gain.gain.value=0;
        context.createMediaElementSource(this.media).connect(gain);gain.connect(context.destination);
        this.context=context;this.gain=gain;
      } catch { /* Fall back to normal media playback if Web Audio is unavailable. */ }
    }
    setPlaying(active,rewind=false) {
      this.active=active;
      if(rewind){this.media.currentTime=0;this.setPace(0);}
      this.refresh();
    }
    setPace(pace) {
      const rate=1+Math.min(12,Math.max(0,pace))*.004;
      if(this.media.playbackRate!==rate)this.media.playbackRate=rate;
    }
    refresh() {
      this.render();
      if(!this.active || !this.enabled || this.volume===0) {
        this.request++;this.pending=false;this.media.pause();
        if(this.context?.state==='running')this.context.suspend().catch(()=>{});
        return;
      }
      // Both calls happen directly in the trusted start/resume/sound gesture.
      this.graph();
      if(this.gain)this.gain.gain.setTargetAtTime(this.volume,this.context.currentTime,.02);
      else this.media.volume=this.volume;
      // Queue resume even if a previous suspend has not finished yet.
      if(this.context)this.context.resume().catch(()=>{});
      if(!this.media.paused || this.pending)return;
      const request=++this.request;this.pending=true;
      try {
        Promise.resolve(this.media.play()).then(()=>{
          if(request!==this.request) {
            if(!this.active || !this.enabled || this.volume===0)this.media.pause();
            return;
          }
          this.pending=false;this.blocked=false;this.render();
        }).catch(()=>{
          if(request!==this.request)return;
          this.pending=false;this.blocked=true;this.render();
        });
      } catch {this.pending=false;this.blocked=true;this.render();}
    }
  };
})();
