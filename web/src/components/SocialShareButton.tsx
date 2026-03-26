import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Closed_envelope_mail from './icons/Closed_envelope_mail.tsx'
import X_logo from './icons/X_logo.tsx'
import Linkedin_logo from './icons/Linkedin_logo.tsx'
import X_logo1 from './icons/X_logo1.tsx'
import Linkedin_logo1 from './icons/Linkedin_logo1.tsx'
import Social_media_facebook_logo from './icons/Social_media_facebook_logo.tsx'
import Closed_envelope_mail1 from './icons/Closed_envelope_mail1.tsx'


    
// Component

        function SocialShareButton({
            variant
        }: {
            variant: 'x' | 'linkedin' | 'facebook' | 'email';
        }) {
            return (
                <a
                    className={"button_button__atjat button_buttonVariantSimple__hzQDj button_buttonSizeM__NexGD"}
                    rel={"noopener"}
                    target={"_blank"}
                >
                    {variant === 'x' && <X_logo1 />}
                    {variant === 'linkedin' && <Linkedin_logo1 />}
                    {variant === 'facebook' && <Social_media_facebook_logo />}
                    {variant === 'email' && <Closed_envelope_mail1 />}
                </a>
            );
        }
    

export default SocialShareButton
