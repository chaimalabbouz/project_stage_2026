from figma_extraction import run_figma_extraction_pipeline
from extractor.tree_extractor import extract_tree_3levels
from extractor.component_reu import extract_reusable_components


from extractor.prepare_payload import prepare_payload

from planner.analyste import run_analyste
from extractor.image_downloader import download_figma_images_and_rewrite_jsons
from extractor.icon_downloader import run_icon_downloader   #  NOUVEAU
from architect.architecte import run_architecte

from extractor.section_extractor import extract_sections

from generator.setup_project import run_setup
from generator.generateur import run_generateur
#from generator.generateur import run_generateur_pages_only
from generator.icon_injector import run_icon_injector       #  NOUVEAU

from generator.val import run_validateur


def main():
   # 
    run_figma_extraction_pipeline()
   # ─── Extraction ───
    print("\n=== ETAPE 1: TREE ===")
    extract_tree_3levels()

    print("\n=== ETAPE 2: COMPONENTS (standalone + variant sets) ===")
    #extract_reusable_components()
    
    print("\n=== ETAPE 3: PAYLOAD ===")
    #prepare_payload()
    
   # ─── Planning ───
    print("\n=== ETAPE 4: ANALYSE ===")
    #run_analyste()
    
    print("\n=== ETAPE 5: ARCHITECTURE ===")
    #run_architecte()
    
    #Sections APRÈS architecture pour mapper les overrides → props React
    print("\n=== ETAPE 6: SECTIONS (avec mapping props + composants imbriqués) ===")
    #extract_sections()
    download_figma_images_and_rewrite_jsons()
    print("\n=== ETAPE 6.5: TÉLÉCHARGEMENT IMAGES + ICÔNES ===")  #  NOUVEAU
    run_icon_downloader()
    # ─── Génération ───
    print("\n=== ETAPE 7: SETUP PROJECT ===")
    run_setup()

    print("\n=== ETAPE 8: GENERATION ===")
    #run_generateur_pages_only()
    run_generateur()
    print("\n=== ETAPE 8.5: INJECTION DES ICÔNES ===")  # ✅ NOUVEAU
    run_icon_injector()
    print("\n=== ETAPE 9: VALIDATION ===")
    #run_validateur()
    
    print("\n=== PIPELINE TERMINE ===")
    

if __name__ == "__main__":
    main()