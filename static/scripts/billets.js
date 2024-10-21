document.getElementById('epreuve-select').addEventListener('change', function() {
  const selectedEpreuve = this.value;
  console.log('Épreuve sélectionnée :', selectedEpreuve);  // Vérifie la sélection dans la console
  if (selectedEpreuve) {
    const targetElement = document.querySelector(selectedEpreuve);
    if (targetElement) {
      targetElement.scrollIntoView({
        behavior: 'smooth',
        block: 'center'  // Centrer l'élément dans la fenêtre
      });
    } else {
      console.error('Element introuvable pour :', selectedEpreuve);
    }
  }
});
