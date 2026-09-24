import os
import qrcode
from fpdf import FPDF
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def create_vinyl_pdf(artist: str, album: str, cover_path: str, tracks: list[str], navidrome_url: str, output_path: str):
    """
    Crea un PDF stampabile in formato custodia CD/Vinile.
    """
    try:
        pdf = FPDF(orientation='L', unit='mm', format='A4') # 297 x 210 mm
        pdf.add_page()
        
        # Sfondo nero opzionale o bianco
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(0, 0, 297, 210, 'F')
        
        # Fronte Custodia (a destra nell'A4 orizzontale)
        # Dimensione standard CD front: 120x120 mm
        front_x = 150
        front_y = 45
        
        # Disegna la copertina
        if cover_path and os.path.exists(cover_path):
            pdf.image(cover_path, x=front_x, y=front_y, w=120, h=120)
        else:
            pdf.set_xy(front_x, front_y)
            pdf.set_font("helvetica", "B", 16)
            pdf.cell(120, 120, f"No Cover: {album}", border=1, align='C')
            
        # Retro Custodia (a sinistra nell'A4 orizzontale)
        # Dimensione standard CD back: 150x118 mm (inclusi bordi laterali)
        back_x = 20
        back_y = 45
        
        # Disegna sfondo grigio chiaro per il retro
        pdf.set_fill_color(240, 240, 240)
        pdf.rect(back_x, back_y, 120, 120, 'F')
        
        pdf.set_xy(back_x + 5, back_y + 10)
        pdf.set_font("helvetica", "B", 14)
        pdf.cell(110, 10, album[:40], align='L')
        
        pdf.set_xy(back_x + 5, back_y + 18)
        pdf.set_font("helvetica", "", 12)
        pdf.cell(110, 10, artist[:40], align='L')
        
        # Disegna Tracklist
        pdf.set_font("helvetica", "", 9)
        y_pos = back_y + 35
        for i, track in enumerate(tracks[:20]): # Max 20 tracce per spazio
            pdf.set_xy(back_x + 5, y_pos)
            pdf.cell(110, 4, f"{i+1}. {track[:60]}", align='L')
            y_pos += 4
            
        # QR Code
        search_query = f"{artist} {album}".replace(" ", "+")
        link = f"{navidrome_url}/app/#/search/{search_query}" if navidrome_url else f"https://music.youtube.com/search?q={search_query}"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=1)
        qr.add_data(link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        qr_path = str(Path(output_path).with_suffix('.png'))
        img.save(qr_path)
        
        # Inserisci QR code in basso a destra del retro
        pdf.image(qr_path, x=back_x + 95, y=back_y + 95, w=20, h=20)
        
        # Linee di ritaglio
        pdf.set_draw_color(200, 200, 200)
        pdf.rect(back_x, back_y, 120, 120, 'D')
        pdf.rect(front_x, front_y, 120, 120, 'D')
        
        pdf.output(output_path)
        os.remove(qr_path)
        return True
    except Exception as e:
        logger.error(f"Errore nella generazione del PDF Vinyl: {e}")
        return False
