import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import DesktopScreenshot from './DesktopScreenshot.tsx'


// Component

        function MarketplaceScreenshots() {
            return (
                <section
                    className={"marketplaceScreenshots_desktopScreenshots__EDDs4"}
                    style={{ "--template-gallery-screenshot-count": "2" }}
                >
                    <DesktopScreenshot
                        hasHighlightBorder={true}
                        maxWidth="1920px"
                        maxHeight="1200px"
                        imgId="2"
                    />
                    <DesktopScreenshot
                        hasHighlightBorder={false}
                        maxWidth="2048px"
                        maxHeight="1280px"
                        imgId="3"
                    />
                </section>
            );
        }
    

export default MarketplaceScreenshots
